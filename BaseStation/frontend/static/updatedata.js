// Initial state
let eventSource = null;

//// Telemetry ////
// Function to update the page when new data comes
function updateDashboard(data, carId) {
  // Hide server warning since we got a live event
  const serverWarn = document.getElementById("serverWarn");
  if (serverWarn) serverWarn.style.display = "none";

  const car = carState(carId);
  car.lastPacket = data;
  car.lastReceived = Date.now();

  // Set the content of each element
  for (const [field, decimals] of Object.entries(NUMERIC_FIELDS)) {
    let value = toNum(data[field]);
    if (field === "throttle" || field === "brake") value /= PEDAL_SCALE; //
    if (TEMP_FIELDS.includes(field) && value < DISCONNECTED_TEMP) value = NaN;
    setNum(carId + field, value, decimals);
  }

  // Car clock time, null when the car has never had a GPS time
  const timestamp = toNum(data.timestamp);
  setText(carId + "timestamp", Number.isFinite(timestamp)
    ? new Date(timestamp * 1000).toLocaleTimeString([], { hour12: false })
    : "—");

  // Color and content of GPS fix status
  if (data.fix === true) setPill(carId + "fix", "GPS fix", "green");
  else setPill(carId + "fix", "No GPS fix", "red");

  updateGauges(carId, data);
  updateMetrics(carId, data);
  renderMetrics(carId);
  updateLiveStatus();
  drawMap(carId);
}

function updateLiveStatus() {
  for (const [carId, car] of Object.entries(cars)) {
    if (car.lastReceived == null) {
      setPill(carId + "live", "No data", "gray");
      continue;
    }
    const age = (Date.now() - car.lastReceived) / 1000;
    if (age < STALE_SECONDS) setPill(carId + "live", "Live", "green");
    else if (age < OFFLINE_SECONDS) setPill(carId + "live", `Stale ${Math.round(age)}s`, "amber");
    else setPill(carId + "live", "Offline", "red");
  }
}


//// Timing ////
// Last race status from the server, used to decide what the race buttons do
let raceStatus = "Not Started";

const STATUS_TONES = { "Running": "green", "Paused": "amber", "Finished": "gray", "Not Started": "gray" };

function updateTiming(data) {
  // Server time
  setText("sysTime", data.sysTime);

  // A different race started (or the page just opened)
  if ((data.raceStartedAt ?? null) !== race.startedAt) {
    race.startedAt = data.raceStartedAt ?? null;
    resetMetrics(race.startedAt);
  }

  race.status = data.status;
  race.seconds = data.raceSeconds ?? null;
  race.receivedAt = performance.now();

  // Shared race info
  raceStatus = data.status;
  setPill("raceStatus", data.status, STATUS_TONES[data.status] ?? "gray");
  setText("raceTime", data.raceTime ?? "0:00.0");
  setText("raceRemaining", formatClock(RACE_SECONDS - (race.seconds ?? 0)));
  setWidth("raceProgress", (race.seconds ?? 0) / RACE_SECONDS * 100);

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
    setText(carId + "paceLastLap", car.lastLapTime);
    setText(carId + "fastestLapTime", car.fastestLapTime);
    updateLaps(carId, car.laps);
  }
}


//// Race control ////
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


//// Theme ////
function toggleTheme() {
  const dark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("theme", dark ? "dark" : "light");
  drawAllMaps();
  Object.keys(cars).forEach(drawLapChart);
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

document.addEventListener("DOMContentLoaded", () => {
  // Show the controls only if this client is already authenticated
  checkAuth();

  // Every car on the page gets its state, so the maps and charts can draw before data arrives
  document.querySelectorAll("canvas[id$='map']").forEach((canvas) => carState(canvas.id.slice(0, -"map".length)));

  buildSpeedTicks();
  buildCurrentLegends();
  Object.keys(cars).forEach(drawLapChart);
  drawAllMaps();

  document.querySelectorAll("[data-map-mode]").forEach((button) => {
    button.addEventListener("click", () => setMapMode(button.dataset.car, button.dataset.mapMode));
  });

  window.addEventListener("resize", drawAllMaps);
  setInterval(updateLiveStatus, 1000);
  setInterval(saveMetrics, 5000);
});
