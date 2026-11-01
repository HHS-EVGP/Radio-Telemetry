let eventSource = null;


// Helper to set text content if element exists
function setText(id, text) {
  const elem = document.getElementById(id);
  if (elem) {
    elem.textContent = text ?? "NNN";
  }
}

// Update DOM with incoming telemetry data point from Server-Sent Events
function updateDashboard(data) {
  // Hide server warning since we got a live event
  const serverWarn = document.getElementById("serverWarn");
  if (serverWarn) serverWarn.style.display = "none";

  // Statuses
  setText("timeStamp", data.timestamp ?? "NNN");
  setText("carId", data.id ?? "NNN");
  setText("throttle", data.throttle ?? "NNN");
  setText("brakePedal", data.brakePedal ?? "NNN");

  // Temperatures
  setText("ambientTemp", data.ambientTemp ?? "NNN");
  setText("motorTemp", data.motorTemp ?? "NNN");
  setText("batt1", data.batt1 ?? "NNN");
  setText("batt2", data.batt2 ?? "NNN");
  setText("batt3", data.batt3 ?? "NNN");
  setText("batt4", data.batt4 ?? "NNN");

  // Turn temperatures red if over 50 degrees
  ["motorTemp", "batt1", "batt2", "batt3", "batt4"].forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      const value = parseFloat(data[id]) ?? 0;
      if (value > 50) {
        element.style.color = "red";
      } else {
        element.style.color = "";
      }
    }
  });

  // Electrical / Performance
  setText("ampHours", data.ampHrs ?? "NNN.NNN");
  setText("estEndAhs", data.endAmpHrs ?? "NNN.NNN");
  setText("voltage", data.voltage ?? "NNN");
  setText("current", data.current ?? "NNN");
  setText("speed", data.speed ?? "NNN");
  setText("miles", data.miles ?? "NNN.NNN");

  // IMU
  setText("roll", data.roll ?? "NNN");
  setText("pitch", data.pitch ?? "NNN");
  setText("heading", data.heading ?? "NNN");
  setText("altitude", data.altitude ?? "NNN");

  // GPS
  setText("gpsX", data.gpsX ?? "NNN");
  setText("gpsY", data.gpsY ?? "NNN");

  // Color and content of GPS fix status
  const gpsFixElem = document.getElementById("gpsFix");
  if (gpsFixElem) {
    if (data.gpsFix === true) {
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
      updateDashboard(data);
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
