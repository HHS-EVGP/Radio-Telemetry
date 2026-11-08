// Initial state
let eventSource = null;

// Helper to set text content if element exists
function setText(id, text) {
  const elem = document.getElementById(id);
  if (elem) {
    elem.textContent = text ?? "NNN";
  }
}

// Helpter to set the text content padded correctly if it's a number
const numFormatter = new Intl.NumberFormat("en-US", {
    minimumIntegerDigits: 3,
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
    useGrouping: false // Prevents thousand separators like commas
  });

function setNum(id, num) {
  const elem = document.getElementById(id);
  if (!elem) return;

  const parsed = parseFloat(num);

  if (isNaN(parsed)) {
    elem.textContent = "NNN";
    return;
  }

  // Format to 3 decimal places
  elem.textContent = numFormatter.format(parsed);
}

// Function to update the page when new data comes
function updateDashboard(data, carId) {
  // Hide server warning since we got a live event
  const serverWarn = document.getElementById("serverWarn");
  if (serverWarn) serverWarn.style.display = "none";

  // Statuses
  setNum(carId + "timeStamp", data.timestamp ?? "NNN");
  setNum(carId + "throttle", data.throttle ?? "NNN");
  setNum(carId + "brake", data.brake ?? "NNN");

  // Temperatures
  setNum(carId + "ambientTemp", data.ambientTemp ?? "NNN");
  setNum(carId + "motorTemp", data.motorTemp ?? "NNN");
  setNum(carId + "batt1", data.batt1 ?? "NNN");
  setNum(carId + "batt2", data.batt2 ?? "NNN");
  setNum(carId + "batt3", data.batt3 ?? "NNN");
  setNum(carId + "batt4", data.batt4 ?? "NNN");

  // Turn temperatures red if over 50 degrees
  ["motorTemp", "batt1", "batt2", "batt3", "batt4"].forEach((elementID) => {
    const element = document.getElementById(carId + elementID);
    if (element) {
      const value = parseFloat(element.textContent);
      if (value > 50) {
        element.style.color = "red";
      } else {
        element.style.color = "";
      }
    }
  });

  // Electrical / Performance
  setNum(carId + "ampHours", data.ampHrs ?? "NNN.NNN");
  setNum(carId + "estEndAhs", data.endAmpHrs ?? "NNN.NNN");
  setNum(carId + "voltage", data.voltage ?? "NNN");
  setNum(carId + "current", data.current ?? "NNN");
  setNum(carId + "speed", data.speed ?? "NNN");
  setNum(carId + "distance", data.distance ?? "NNN.NNN");

  // IMU
  setNum(carId + "roll", data.roll ?? "NNN");
  setNum(carId + "pitch", data.pitch ?? "NNN");
  setNum(carId + "heading", data.heading ?? "NNN");
  setNum(carId + "altitude", data.altitude ?? "NNN");

  // GPS
  setNum(carId + "gpsX", data.gpsX ?? "NNN");
  setNum(carId + "gpsY", data.gpsY ?? "NNN");

  // Color and content of GPS fix status
  const gpsFixElem = document.getElementById(carId + "gpsFix");
  if (gpsFixElem) {
    if (data.fix === "true") {
      gpsFixElem.textContent = "Yes";
      gpsFixElem.style.color = "green";
    } else {
      gpsFixElem.textContent = "No";
      gpsFixElem.style.color = "red";
    }
  }
}

function updateTiming(data) {
  // Server time
  setText("sysTime", data.systime ?? "NNN");
}

// Connect to Server-Sent Events stream
function connectSSE() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource("/stream");

  // Disaible the server warning if we establish a conection
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
