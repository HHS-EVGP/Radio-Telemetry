// Initial state
let eventSource = null;

// Helper to set text content if element exists
function setText(id, text) {
  const elem = document.getElementById(id);
  if (elem) {
    elem.textContent = text ?? "NNN";
  }
}

// Helper to set the text content padded correctly if it's a number
const numFormatter = new Intl.NumberFormat("en-US", {
  minimumIntegerDigits: 3,
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
  useGrouping: false, // Prevents thousand separators like commas
});

function setNum(id, num) {
  const elem = document.getElementById(id);
  if (!elem) return;

  // null/undefined (missing or NAN on the car) parse to NaN
  const parsed = parseFloat(num);
  elem.textContent = isNaN(parsed) ? "NNN" : numFormatter.format(parsed);
}

// Numeric telemetry fields. Each one is shown in the element with id <carId><field>
const NUMERIC_FIELDS = [
  "timestamp", "throttle", "brake",
  "ambientTemp", "motorTemp", "batt1", "batt2", "batt3", "batt4",
  "ampHrs", "voltage", "current", "speed", "distance",
  "roll", "pitch", "heading", "altitude",
  "gpsX", "gpsY",
];

// Temperatures that turn red above HOT_TEMP degrees C
const WATCHED_TEMPS = ["motorTemp", "batt1", "batt2", "batt3", "batt4"];
const HOT_TEMP = 50;

// Function to update the page when new data comes
function updateDashboard(data, carId) {
  // Hide server warning since we got a live event
  const serverWarn = document.getElementById("serverWarn");
  if (serverWarn) serverWarn.style.display = "none";

  NUMERIC_FIELDS.forEach((field) => setNum(carId + field, data[field]));

  WATCHED_TEMPS.forEach((field) => {
    const elem = document.getElementById(carId + field);
    if (elem) elem.style.color = data[field] > HOT_TEMP ? "red" : "";
  });

  // Color and content of GPS fix status
  const fixElem = document.getElementById(carId + "fix");
  if (fixElem) {
    fixElem.textContent = data.fix === true ? "Yes" : "No";
    fixElem.style.color = data.fix === true ? "green" : "red";
  }
}

// Last race status from the server, used to decide what the race buttons do
let raceStatus = "Not Started";

function updateTiming(data) {
  // Server time
  setText("sysTime", data.sysTime);

  // Shared race info
  raceStatus = data.status;
  setText("raceStatus", data.status);
  setText("raceTime", data.raceTime);

  const started = raceStatus === "Running" || raceStatus === "Paused";
  const startStop = document.getElementById("raceStartStop");
  if (startStop) startStop.textContent = started ? "Stop Race" : "Start Race";

  const pauseResume = document.getElementById("racePauseResume");
  if (pauseResume) {
    pauseResume.textContent = raceStatus === "Paused" ? "Resume Race" : "Pause Race";
    pauseResume.disabled = !started;
  }

  // Per car info
  for (const [carId, car] of Object.entries(data.cars ?? {})) {
    setText(carId + "laps", car.laps);
    setText(carId + "lapTime", car.lapTime);
    setText(carId + "lastLapTime", car.lastLapTime);
    setText(carId + "fastestLapTime", car.fastestLapTime);
    setNum(carId + "estEndAmpHrs", car.estEndAmpHrs);
  }
}

// Show the race controls if authenticated, otherwise show the access code form
function showControls(authed) {
  document.querySelectorAll(".raceControls").forEach((elem) => {
    elem.style.display = authed ? "" : "none";
  });
  const authForm = document.getElementById("authControls");
  if (authForm) authForm.style.display = authed ? "none" : "";
}

async function checkAuth() {
  try {
    const response = await fetch("/auth");
    const data = await response.json();
    showControls(data.authed === true);
  } catch (err) {
    console.error("Error checking authentication:", err);
  }
}

async function authenticate(code) {
  const authError = document.getElementById("authError");
  try {
    const response = await fetch("/auth", { method: "POST", body: code });
    const data = await response.json();
    if (authError) authError.style.display = data.authed ? "none" : "block";
    showControls(data.authed === true);
  } catch (err) {
    console.error("Error authenticating:", err);
    alert("Unable to reach the server");
  }
}

function playLapSound() {
  const lapSound = document.getElementById("lapSound");
  if (lapSound) {
    lapSound.currentTime = 0;
    lapSound.play().catch((err) => console.error("Error playing lap sound:", err));
  }
}

// Send a timing command to the server. Every client gets the result through SSE
// Returns true if the command succeeded
async function sendCommand(url) {
  try {
    const response = await fetch(url, { method: "POST" });
    // Server errors (500) return HTML instead of JSON, so the .catch wraps it in a json
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) {
      showControls(false);
      return false;
    }
    if (!response.ok) {
      alert(data.error ?? "Command failed");
      return false;
    }
    updateTiming(data);
    return true;
  } catch (err) {
    console.error("Error sending command:", err);
    alert("Unable to reach the server");
    return false;
  }
}

function raceStartStop() {
  if (raceStatus === "Running" || raceStatus === "Paused") {
    if (confirm("Stop the race?")) sendCommand("/race/stop");
  } else {
    sendCommand("/race/start");
  }
}

function racePauseResume() {
  sendCommand(raceStatus === "Paused" ? "/race/resume" : "/race/pause");
}

async function changeLap(carId, delta) {
  if ((await sendCommand(`/laps/${carId}/${delta}`)) && delta === "plus") {
    playLapSound();
  }
}

// Connect to Server-Sent Events stream
function connectSSE() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource("/stream");

  // Hide the server warning if we establish a connection
  eventSource.onopen = function () {
    const serverWarn = document.getElementById("serverWarn");
    if (serverWarn) serverWarn.style.display = "none";
  };

  // Update the dashboard when we get telemetry data
  eventSource.addEventListener("telemetry", function (event) {
    try {
      const data = JSON.parse(event.data);
      updateDashboard(data, data.id);
    } catch (err) {
      console.error("Error parsing SSE data:", err);
    }
  });

  // Update the timer when we get timing data
  eventSource.addEventListener("timing", function (event) {
    try {
      const data = JSON.parse(event.data);
      updateTiming(data);
    } catch (err) {
      console.error("Error parsing SSE data:", err);
    }
  });

  // Show the server warning if we lose the connection
  eventSource.onerror = function (err) {
    const serverWarn = document.getElementById("serverWarn");
    if (serverWarn) serverWarn.style.display = "block";
  };
}

// Start Server-Sent Events connection
connectSSE();

// Show the controls only if this client is already authenticated
document.addEventListener("DOMContentLoaded", checkAuth);
