// Start initial chart instances
function startCharts() {
  fetch('/getdata')
    .then(response => response.json())
    .then(data => {

      // Destroy old charts if they exist
      if (window.throttleBrakeChart instanceof Chart) {
        window.throttleBrakeChart.destroy();
      }
      if (window.gpsChart instanceof Chart) {
        window.gpsChart.destroy();
      }

      const barCtx = document.getElementById('throttleBrakeChart');

      window.throttleBrakeChart = new Chart(barCtx, {
        type: 'bar',
        data: {
          labels: ['Throttle', 'Brake Pedal'],
          datasets: [{
            data: [data.throttle ?? 0, data.brake_pedal ?? 0],
            backgroundColor: ['rgba(68, 192, 95, 0.75)', 'rgba(255, 0, 0, 0.75)'],
            borderColor: ['rgb(68, 192, 95)', 'rgb(255, 0, 0)'],
            borderWidth: 1
          }]
        },
        options: {
          maintainAspectRatio: false,
          animation: false,
          indexAxis: 'y',
          plugins: {
            legend: {
              display: false
            }
          },
          scales: {
            x: {
              beginAtZero: true,
              max: 1000, // Set the maximum value for the x-axis
            },
            y: {
              ticks: {
                font: {
                  size: 16 // Adjust the font size for the labels
                }
              }
            }
          }
        }
      });

      const ctx = document.getElementById('gpsplot');

      window.gpsChart = new Chart(ctx, {
        type: 'line',
        data: {
          datasets: [{
            data: [{
              x: data.GPS_x,
              y: data.GPS_y
            }],
            backgroundColor: 'rgb(54, 67, 126)',
            borderColor: 'rgb(54, 67, 126)', // Set line color
            fill: false, // Disable filling under the line
            tension: 1 // Line smoothness (0 for straight lines)
          }]
        },
        options: {
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: false,
            }
          },
          animation: false,
          scales: {
            x: {
              type: 'linear', // Ensure x-axis is linear for scatter data
              position: 'bottom'
            }
          }
        }
      });
    });
}


// Authenticate lap controls
function authenticateLapControls(code) {
  fetch('/usrauth', {
    method: 'POST',
    body: code,
  })

    .then(response => {
      if (response.status == 200) {
        document.getElementById('lapcontrols').style.display = 'block';
        document.getElementById('authlapcontrols').style.display = 'none';
      }
      else if (response.status == 401) {
        new bootstrap.Modal(document.getElementById('lapauthmodal')).show();
        document.getElementById('autherror').style.display = 'block';
      }
      else {
        console.error('Unknown Auth Error:', response);
      }
    });
}


// Update a variable on the server
function updateServerVariable(updatecode) {
  // Hide data warning if needed
  document.getElementById('nodatawarn').style.display = 'none';

  // Redraw the charts to clear them on race start and stop
  if (updatecode == 'togglerace') {
    startCharts();
  }

  fetch('/usrupdate', {
    method: 'POST',
    body: updatecode,
  })
    // If no data to start race with, display warning
    .then(response => {
      if (response.status === 422) {
        document.getElementById('nodatawarn').style.display = 'block';
      }

      // Check for sucessful lap+, and play sound if so
      return response.text().then(text => {
        if (text === 'Play Sound' && response.status === 200) {
          playLapSound();
        }
      })
    });
}

// Play the lap sound
function playLapSound() {
  if (window.racing ?? false == true) {
    document.getElementById('lapsound').play();
  }
}

// Fetch data
function updateData() {
  fetch('/getdata')
    .then(response => {
      if (!response.ok) throw new Error('Server offline');
      return response.json();
    })
    .then(data => {

      // Statuses
      document.getElementById('systime').textContent = data.systime ?? 'NNN';
      document.getElementById('timestamp').textContent = data.timestamp ?? 'NNN';

      // Update the throttle and brake chart
      window.throttleBrakeChart.data.datasets[0].data = [data.throttle ?? 0, data.brake_pedal ?? 0];
      window.throttleBrakeChart.update();

      // Temperatures
      document.getElementById('motor_temp').textContent = data.motor_temp ?? 'NNN';
      document.getElementById('batt_1').textContent = data.batt_1 ?? 'NNN';
      document.getElementById('batt_2').textContent = data.batt_2 ?? 'NNN';
      document.getElementById('batt_3').textContent = data.batt_3 ?? 'NNN';
      document.getElementById('batt_4').textContent = data.batt_4 ?? 'NNN';

      // Check if any temperature is above 50 degrees and turn them red
      ['motor_temp', 'batt_1', 'batt_2', 'batt_3', 'batt_4'].forEach(id => {
        const element = document.getElementById(id);
        const value = parseFloat(data[id]) ?? 0;
        if (value > 50) {
          element.style.color = 'red';
        } else {
          element.style.color = ''; // Reset to default
        }
      });

      // General
      document.getElementById('amp_hours').textContent = data.amp_hours ?? 'NNN.NNN';
      document.getElementById('voltage').textContent = data.voltage ?? 'NNN';
      document.getElementById('current').textContent = data.current ?? 'NNN';
      document.getElementById('speed').textContent = data.speed ?? 'NNN';
      document.getElementById('miles').textContent = data.miles ?? 'NNN.NNN';

      // Estimated end amp hours
      document.getElementById('estendahs').textContent = data.endAmphrs ?? 'NNN.NNN';

      // Timimg
      document.getElementById('laps').textContent = data.laps ?? 'NN';
      document.getElementById('laptime').textContent = data.laptime ?? 'NNN'
      document.getElementById('lastlaptime').textContent = data.lastlaptime ?? 'NNN';
      document.getElementById('fastestlaptime').textContent = data.fastestlaptime ?? 'NNN';
      document.getElementById('racetime').textContent = data.racetime ?? 'NNN';

      // If racetime_minutes is not 0, display it
      if (data.racetime_minutes != 0) {
        document.getElementById('racetime_minutes').textContent = data.racetime_minutes;
      }

      // Display of race controls or of authenticate button
      if (data.authed == true) {
        document.getElementById('lapcontrols').style.display = 'block';
        document.getElementById('authlapcontrols').style.display = 'none';
      }
      else {
        document.getElementById('lapcontrols').style.display = 'none';
        document.getElementById('authlapcontrols').style.display = 'block';
      }

      // Make data.racing a global variable
      window.racing = data.racing;

      const racing = data.racing ?? false;
      const paused = data.paused ?? false;

      // Start/stop race button and modal start/stop
      if (racing == true || paused == true) {
        document.getElementById('racing').textContent = "Stop";
        document.getElementById('startorstop').textContent = "stop the current";

        // Show paused button
        document.getElementById('paused').style.display = 'inline-block';

      }
      if (racing == false && paused == false) {
        document.getElementById('racing').textContent = "Start Race";
        document.getElementById('startorstop').textContent = "start a";

        // Hide paused button
        document.getElementById('paused').style.display = 'none';
      }

      // Pause/Unpause button
      if (paused == true) {
        document.getElementById('paused').textContent = "Resume";
      }
      else {
        document.getElementById('paused').textContent = "Pause";
      }

      // GPS
      document.getElementById('GPS_x').textContent = data.GPS_x ?? 'NNN';
      document.getElementById('GPS_y').textContent = data.GPS_y ?? 'NNN';

      // Update scatter plot with new gps data
      window.gpsChart.data.datasets[0].data.push({
        x: data.GPS_x,
        y: data.GPS_y
      });

      window.gpsChart.update();

      // Hide server warning since we got data
      document.getElementById("serverwarn").style.display = "none";

    })
    .catch(err => {
      // Show server warning
      document.getElementById('serverwarn').style.display = "block";
    });
}
setInterval(updateData, 250); // Update every 250ms


// Functions to count the clock
function countLapTime() {
  if (window.racing == true) {
    const laptimeElem = document.getElementById('laptime');
    let laptime = parseFloat(laptimeElem.textContent) ?? 0;
    laptime += 0.1;

    // Clean view
    laptime = laptime.toFixed(1);

    laptimeElem.textContent = laptime;
  }
}
setInterval(countLapTime, 100);

function countRaceTime() {
  if (window.racing == true) {
    const racetimeElem = document.getElementById('racetime');
    const racetime_minutesElem = document.getElementById('racetime_minutes')

    let racetime = parseFloat(racetimeElem.textContent) ?? 0;
    let racetime_minutes = racetime_minutesElem.textContent;

    racetime += 0.1;

    // If racetime_minutes is nothing, treat it as 0
    if (racetime_minutes == "") {
      racetime_minutes = 0;
    }
    else {
      racetime_minutes = parseFloat(racetime_minutes);
    }

    // If racetime >= 60, add it to minutes
    if (racetime >= 60) {
      let minutes2add = Math.floor(racetime / 60);
      racetime_minutes += minutes2add;
      racetime -= minutes2add * 60
    }

    // Clean view
    if (racetime < 10 && racetime_minutes != 0) {
      racetime = '0' + racetime.toFixed(1);
    }
    else {
      racetime = racetime.toFixed(1)
    }

    // Update values
    racetimeElem.textContent = racetime;
    if (racetime_minutes != 0) {
      racetime_minutesElem.textContent = racetime_minutes + ":";
    }
  }
}
setInterval(countRaceTime, 100);

// Call startCharts on window load and resize
window.addEventListener('load', startCharts);
window.addEventListener('resize', startCharts);


// Hide lap controls and warnings
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('lapcontrols').style.display = 'none';
  document.getElementById('autherror').style.display = 'none';

  document.getElementById('nodatawarn').style.display = 'none';
  document.getElementById('serverwarn').style.display = "none";
});
