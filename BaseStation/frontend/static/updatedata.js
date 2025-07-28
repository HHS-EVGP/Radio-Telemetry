// Start initial chart instances
function startCharts() {
  fetch("/getdata")
    .then((response) => response.json())
    .then((data) => {
      // Destroy old charts if they exist
      if (window.throttleBrakeChart instanceof Chart) {
        window.throttleBrakeChart.destroy();
      }
      if (window.gpsChart instanceof Chart) {
        window.gpsChart.destroy();
      }

      const barCtx = document.getElementById("throttleBrakeChart");

      window.throttleBrakeChart = new Chart(barCtx, {
        type: "bar",
        data: {
          labels: ["Throttle", "Brake Pedal"],
          datasets: [
            {
              data: [data.throttle ?? 0, data.brakePedal ?? 0],
              backgroundColor: [
                "rgba(68, 192, 95, 0.75)",
                "rgba(255, 0, 0, 0.75)",
              ],
              borderColor: ["rgb(68, 192, 95)", "rgb(255, 0, 0)"],
              borderWidth: 1,
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          animation: false,
          indexAxis: "y",
          plugins: {
            legend: {
              display: false,
            },
          },
          scales: {
            x: {
              beginAtZero: true,
              max: 1000, // Max value for the x-axis
            },
            y: {
              ticks: {
                font: {
                  size: 16, // Font size for labels
                },
              },
            },
          },
        },
      });

      const ctx = document.getElementById("gpsplot");

      window.gpsChart = new Chart(ctx, {
        type: "line",
        data: {
          datasets: [
            {
              data: [
                {
                  x: data.gpsX,
                  y: data.gpsY,
                },
              ],
              backgroundColor: "rgb(54, 67, 126)",
              borderColor: "rgb(54, 67, 126)", // Line color
              fill: false, // No filling under the line
              tension: 1, // Line smoothness (0 for straight lines)
            },
          ],
        },
        options: {
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false,
            },
          },
          animation: false,
          scales: {
            x: {
              type: "linear", // Ensure x-axis is linear for scatter data
              position: "bottom",
            },
          },
        },
      });
    });
}


// Authenticate lap controls
function authenticateLapControls(code) {
  fetch("/usrauth", {
    method: "POST",
    body: code,
  }).then((response) => {
    if (response.status == 200) {
      document.getElementById("lapControls").style.display = "block";
      document.getElementById("authLapControls").style.display = "none";
    } else if (response.status == 401) {
      new bootstrap.Modal(document.getElementById("lapAuthModal")).show();
      document.getElementById("authError").style.display = "block";
    } else {
      console.error("Unknown Auth Error:", response);
    }
  });
}


// Update a variable on the server
function updateServerVariable(updateCode) {
  // Hide data warning if needed
  document.getElementById("noDataWarn").style.display = "none";

  // Redraw the charts to clear them on race start and stop
  if (updateCode == "togglerace") {
    startCharts();
  }

  fetch("/usrupdate", {
    method: "POST",
    body: updateCode,
  })
    // If no data to start race with, display warning
    .then(async (response) => {
      if (response.status === 422) {
        document.getElementById("noDataWarn").style.display = "block";
      }

      // Check for sucessful lap+, and play sound if so
      const text = await response.text();
      if (text === "Play Sound" && response.status === 200) {
        playLapSound();
      }
    });
}


// Play the lap sound
function playLapSound() {
  if (window.racing ?? false == true) {
    document.getElementById("lapSound").play();
  }
}


// Fetch data
function getData() {
  fetch("/getdata")
    .then((response) => {
      if (!response.ok) throw new Error("Server offline");
      return response.json();
    })
    .then((data) => {
      // Statuses
      document.getElementById("sysTime").textContent = data.systime ?? "NNN";
      document.getElementById("timeStamp").textContent =
        data.timestamp ?? "NNN";

      // Update the throttle and brake chart
      window.throttleBrakeChart.data.datasets[0].data = [
        data.throttle ?? 0,
        data.brakePedal ?? 0,
      ];
      window.throttleBrakeChart.update();

      // Temperatures
      document.getElementById("motorTemp").textContent =
        data.motorTemp ?? "NNN";
      document.getElementById("batt1").textContent = data.batt1 ?? "NNN";
      document.getElementById("batt2").textContent = data.batt2 ?? "NNN";
      document.getElementById("batt3").textContent = data.batt3 ?? "NNN";
      document.getElementById("batt4").textContent = data.batt4 ?? "NNN";

      // Check if any temperature is above 50 degrees and turn them red
      ["motorTemp", "batt1", "batt2", "batt3", "batt4"].forEach((id) => {
        const element = document.getElementById(id);
        const value = parseFloat(data[id]) ?? 0;
        if (value > 50) {
          element.style.color = "red";
        } else {
          element.style.color = ""; // Reset to default
        }
      });

      // General
      document.getElementById("ampHours").textContent = data.ampHrs ?? "NNN.NNN";
      document.getElementById("voltage").textContent = data.voltage ?? "NNN";
      document.getElementById("current").textContent = data.current ?? "NNN";
      document.getElementById("speed").textContent = data.speed ?? "NNN";
      document.getElementById("miles").textContent = data.miles ?? "NNN.NNN";

      // Estimated end amp hours
      document.getElementById("estEndAhs").textContent =
        data.endAmpHrs ?? "NNN.NNN";

      // Timimg
      document.getElementById("laps").textContent = data.laps ?? "NN";
      document.getElementById("lapTime").textContent = data.lapTime ?? "NNN";
      document.getElementById("lastLapTime").textContent = data.lastLapTime ?? "NNN";
      document.getElementById("fastestLapTime").textContent = data.fastestLapTime ?? "NNN";
      document.getElementById("raceTime").textContent = data.raceTime ?? "NNN";

      // If racetime_minutes is not 0, display it
      if (data.raceTimeMinutes != 0) {
        document.getElementById("raceTimeMinutes").textContent =
          data.raceTimeMinutes;
      }

      // Display of race controls or of authenticate button
      if (data.authed == true) {
        document.getElementById("lapControls").style.display = "block";
        document.getElementById("authLapControls").style.display = "none";
      } else {
        document.getElementById("lapControls").style.display = "none";
        document.getElementById("authLapControls").style.display = "block";
      }

      // Make data.racing a global variable
      window.racing = data.racing;

      const racing = data.racing ?? false;
      const paused = data.paused ?? false;

      // Start/stop race button and modal start/stop
      if (racing == true || paused == true) {
        document.getElementById("racing").textContent = "Stop";
        document.getElementById("startOrStop").textContent = "stop the current";

        // Show paused button
        document.getElementById("paused").style.display = "inline-block";
      }
      if (racing == false && paused == false) {
        document.getElementById("racing").textContent = "Start Race";
        document.getElementById("startOrStop").textContent = "start a";

        // Hide paused button
        document.getElementById("paused").style.display = "none";
      }

      // Pause/Unpause button
      if (paused == true) {
        document.getElementById("paused").textContent = "Resume";
      } else {
        document.getElementById("paused").textContent = "Pause";
      }

      // GPS
      document.getElementById("gpsX").textContent = data.gpsX ?? "NNN";
      document.getElementById("gpsY").textContent = data.gpsY ?? "NNN";

      // Update scatter plot with new gps data
      window.gpsChart.data.datasets[0].data.push({
        x: data.gpsX,
        y: data.gpsY,
      });

      window.gpsChart.update();

      // Rotate out old points if needed
      const maxGpsPoints = 300;
      if (window.gpsChart.data.datasets[0].data.length > maxGpsPoints) {
        window.gpsChart.data.datasets[0].data.shift();
      }

      // Hide server warning since we got data
      document.getElementById("serverWarn").style.display = "none";
    })
    .catch((err) => {
      // Show server warning
      document.getElementById("serverWarn").style.display = "block";
    });
}
setInterval(getData, 250); // Every 250ms


// Functions to count the clock
function countLapTime() {
  if (window.racing == true) {
    const lapTimeElem = document.getElementById("lapTime");
    let lapTime = parseFloat(lapTimeElem.textContent) ?? 0;
    lapTime += 0.1;
    lapTime = lapTime.toFixed(1);
    lapTimeElem.textContent = lapTime;
  }
}
setInterval(countLapTime, 100);


function countRaceTime() {
  if (window.racing == true) {
    const raceTimeElem = document.getElementById("raceTime");
    const raceTimeMinutesElem = document.getElementById("raceTimeMinutes");

    let raceTime = parseFloat(raceTimeElem.textContent) ?? 0;
    let raceTimeMinutes = raceTimeMinutesElem.textContent;

    raceTime += 0.1;

    // If racetime_minutes is nothing, treat it as 0
    if (raceTimeMinutes == "") {
      raceTimeMinutes = 0;
    } else {
      raceTimeMinutes = parseFloat(raceTimeMinutes);
    }

    // If racetime >= 60, add it to minutes
    if (raceTime >= 60) {
      let minutes2add = Math.floor(raceTime / 60);
      raceTimeMinutes += minutes2add;
      raceTime -= minutes2add * 60;
    }

    // Clean view
    if (raceTime < 10 && raceTimeMinutes != 0) {
      raceTime = "0" + raceTime.toFixed(1);
    } else {
      raceTime = raceTime.toFixed(1);
    }

    // Update values
    raceTimeElem.textContent = raceTime;
    if (raceTimeMinutes != 0) {
      raceTimeMinutesElem.textContent = raceTimeMinutes + ":";
    }
  }
}
setInterval(countRaceTime, 100);


// Call startCharts on window load and resize
window.addEventListener("load", startCharts);
window.addEventListener("resize", startCharts);


// Hide lap controls and warnings
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("lapControls").style.display = "none";
  document.getElementById("authError").style.display = "none";
  document.getElementById("noDataWarn").style.display = "none";
  document.getElementById("serverWarn").style.display = "none";
});
