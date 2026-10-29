// Default state
window.racing = false;
let eventSource = null;

// Function to authenticate lap controls
function authenticateLapControls(code) {
  fetch("/usrauth", {
    method: "POST",
    body: code,
  }).then((response) => {
    const lapControls = document.getElementById("lapControls");
    const authLapControls = document.getElementById("authLapControls");
    const authError = document.getElementById("authError");

    // Set up controls if we're authorized
    if (response.status === 200) {
      if (lapControls) lapControls.style.display = "block";
      if (authLapControls) authLapControls.style.display = "none";
      if (authError) authError.style.display = "none";
    }

    // Prompt the user if the password is incorrect
    else if (response.status === 401) {
      const modal = document.getElementById("lapAuthModal");
      if (modal && window.bootstrap) {
        new bootstrap.Modal(modal).show();
      }
      if (authError) authError.style.display = "block";
    }

    // Log other erros
    else {
      console.error("Unknown Auth Error:", response);
    }
  });
}

// Function to update a variable on the server
function updateServerVariable(updateCode) {
  // Hide the nodata warn if we need to before sending a message
  const noDataWarn = document.getElementById("noDataWarn");
  if (noDataWarn) noDataWarn.style.display = "none";

  fetch("/usrupdate", {
    method: "POST",
    body: updateCode,
  }).then(async (response) => {
    // If the server resondes with a no data error, tell the server
    if (response.status === 422 && noDataWarn) {
      noDataWarn.style.display = "block";
    }

    // If we get the go ahead from the server, play the sound
    const text = await response.text();
    if (text === "Play Sound" && response.status === 200) {
      playLapSound();
    }
  });
}

// Play the lap sound
function playLapSound() {
  if (window.racing === true) {
    const lapSound = document.getElementById("lapSound");
    if (lapSound) {
      lapSound.play();
    }
  }
}

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
  setText("sysTime", data.systime ?? "NNN");
  setText("timeStamp", data.timestamp ?? "NNN");
  setText("carId", data.carId ?? "NNN");
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

  // Timing
  setText("laps", data.laps ?? "NN");
  setText("lapTime", data.lapTime ?? "NNN");
  setText("lastLapTime", data.lastLapTime ?? "NNN");
  setText("fastestLapTime", data.fastestLapTime ?? "NNN");
  setText("raceTime", data.raceTime ?? "NNN");

  // Display race time minutes if it is relevant
  const raceTimeMinutesElem = document.getElementById("raceTimeMinutes");
  if (raceTimeMinutesElem) {
    raceTimeMinutesElem.textContent = (data.raceTimeMinutes != 0 && data.raceTimeMinutes != null) ? data.raceTimeMinutes : "";
  }

  // Auth controls visibility
  const lapControls = document.getElementById("lapControls");
  const authLapControls = document.getElementById("authLapControls");
  if (lapControls && authLapControls) {
    if (data.authed === true) {
      lapControls.style.display = "block";
      authLapControls.style.display = "none";
    } else {
      lapControls.style.display = "none";
      authLapControls.style.display = "block";
    }
  }

  // Global racing state
  window.racing = data.racing ?? false;
  const racing = data.racing ?? false;
  const paused = data.paused ?? false;

  // Race start/stop and pause buttons
  const racingBtn = document.getElementById("racing");
  const startOrStop = document.getElementById("startOrStop");
  const pausedBtn = document.getElementById("paused");

  if (racingBtn && startOrStop && pausedBtn) {
    if (racing === true || paused === true) {
      racingBtn.textContent = "Stop";
      startOrStop.textContent = "stop the current";
      pausedBtn.style.display = "inline-block";
    } else {
      racingBtn.textContent = "Start Race";
      startOrStop.textContent = "start a";
      pausedBtn.style.display = "none";
    }

    if (paused === true) {
      pausedBtn.textContent = "Resume";
    } else {
      pausedBtn.textContent = "Pause";
    }
  }

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

  // When we get the message from the server, parse the data
  eventSource.onmessage = function (event) {
    try {
      const data = JSON.parse(event.data);
      updateDashboard(data);
    } catch (err) {
      console.error("Error parsing SSE data:", err);
    }
  };

  // Show the server warning if we lose the connection
  eventSource.onerror = function (err) {
    const serverWarn = document.getElementById("serverWarn");
    if (serverWarn) serverWarn.style.display = "block";
  };
}

// Function to locally count the laptime
function countLapTime() {
  if (window.racing === true) {
    const lapTimeElem = document.getElementById("lapTime");
    if (lapTimeElem) {
      let lapTime = parseFloat(lapTimeElem.textContent) ?? 0;
      if (!isNaN(lapTime)) {
        lapTime += 0.1;
        lapTimeElem.textContent = lapTime.toFixed(1);
      }
    }
  }
}
setInterval(countLapTime, 100);

// Function to loaclly
function countRaceTime() {
  if (window.racing === true) {
    const raceTimeElem = document.getElementById("raceTime");
    const raceTimeMinutesElem = document.getElementById("raceTimeMinutes");

    if (raceTimeElem && raceTimeMinutesElem) {
      let raceTime = parseFloat(raceTimeElem.textContent) ?? 0;
      let raceTimeMinutes = raceTimeMinutesElem.textContent;

      if (!isNaN(raceTime)) {
        raceTime += 0.1;

        // Set racetime minutes to 0 if its empty (for the sake of our math)
        if (raceTimeMinutes === "") {
          raceTimeMinutes = 0;
        } else {
          raceTimeMinutes = parseFloat(raceTimeMinutes);
          if (isNaN(raceTimeMinutes)) raceTimeMinutes = 0;
        }

        // Use the remainder operator and truncated division to seperate minutes and seconds
        raceTimeMinutes = Math.trunc(raceTime / 60);

        raceTime %= 60;

        // Update the display with the new values
        raceTimeElem.textContent = raceTime;
        if (raceTimeMinutes !== 0) {
          raceTimeMinutesElem.textContent = raceTimeMinutes + ":";
        }
      }
    }
  }
}
setInterval(countRaceTime, 100);

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  const lapControls = document.getElementById("lapControls");
  if (lapControls) lapControls.style.display = "none";

  const authError = document.getElementById("authError");
  if (authError) authError.style.display = "none";

  const noDataWarn = document.getElementById("noDataWarn");
  if (noDataWarn) noDataWarn.style.display = "none";

  const serverWarn = document.getElementById("serverWarn");
  if (serverWarn) serverWarn.style.display = "none";

  // Start Server-Sent Events connection
  connectSSE();
});
