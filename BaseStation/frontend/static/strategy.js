//// Race clock ////
// Race time comes from the timing serer-sent events and is advanced locally between them
const race = { status: "Not Started", seconds: null, startedAt: null, receivedAt: 0 };

function raceActive() {
  return race.status === "Running" || race.status === "Paused";
}

function raceSecondsNow() {
  if (race.seconds == null) return null;
  if (race.status !== "Running") return race.seconds; // If we're paused
  return race.seconds + (performance.now() - race.receivedAt) / 1000;
}


//// Per car state for the pace and energy metrics ////
const cars = {};

function newCarState() {
  return {
    lastPacket: null,
    lastReceived: null, // Last time we got a packet
    wh: null, // Wh used, from the car
    ampHrs: null,
    recent: [], // {t, wh, distance} for the last RECENT_SECONDS of race time
    batt: { voc: null, r: null, lowCount: 0 }, // Latest estimate from the car, and how many in a row were low
    laps: [], // Completed laps
    lap: null, // The lap in progress
    lapCount: null,
    track: [], // [x, y] GPS points for the map outline
    trail: [], // [x, y, current] most recent GPS points
    mapMode: "live",
  };
}

function carState(carId) {
  cars[carId] ??= newCarState(); // a ??= b is a shorthand for a = a ?? b
  return cars[carId];
}

// Parts of the car state that are saved so a page reload mid race keeps its history
const SAVED_TEMPLATE = ["recent", "laps", "lap", "lapCount", "track"];

function saveMetrics() {
  if (race.startedAt == null) return;
  const saved = { startedAt: race.startedAt, cars: {} };
  for (const [carId, car] of Object.entries(cars)) {
    saved.cars[carId] = Object.fromEntries(SAVED_TEMPLATE.map((key) => [key, car[key]]));
    saved.cars[carId].batt = { voc: car.batt.voc, r: car.batt.r, lowCount: car.batt.lowCount };
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  } catch (err) {
    console.error("Error saving race metrics:", err);
  }
}

// A new race started (or the page just opened), so start the metrics and map outline over,
// or restore the saved ones if they're from this race
function resetMetrics(startedAt) {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch (err) {
    saved = null;
  }

  // The saved cars might not have sent any data to this page yet
  const carIds = new Set([...Object.keys(cars), ...Object.keys(saved?.cars ?? {})]); // Merge the data seen live with loaded data
  for (const carId of carIds) {
    const car = carState(carId);
    const fresh = newCarState();
    Object.assign(car, Object.fromEntries(SAVED_TEMPLATE.map((key) => [key, fresh[key]]))); // Assign the contents of car form newCarState
    car.batt.lowCount = 0;

    const savedCar = saved?.startedAt === startedAt ? saved.cars?.[carId] : null;
    if (savedCar) {
      Object.assign(car, Object.fromEntries(SAVED_TEMPLATE.map((key) => [key, savedCar[key] ?? fresh[key]])));
      Object.assign(car.batt, savedCar.batt);
    }
    drawMap(carId);
    drawLapChart(carId);
  }
}

function allowedPower(car, t) {
  if (car.wh == null || t == null) return null;
  const remaining = Math.max(30, RACE_SECONDS - t);
  return Math.max(0, BUDGET_WH - car.wh) / remaining * 3600; // Allowed power stops at 0 so that it does not grow after it is all used
}

// Lap speed that would use exactly this much power on average
// power = mph * Wh per mile = SLOPE * mph^2 + INTERCEPT * mph, solved for mph
function targetSpeed(power) {
  if (power == null) return null;
  const a = WH_PER_MILE_SLOPE;
  const b = WH_PER_MILE_INTERCEPT;
  return (-b + Math.sqrt(b * b + 4 * a * power)) / (2 * a);
}
function recentRates(car) {

  const first = car.recent[0];
  const last = car.recent[car.recent.length - 1];
  if (!first || last.t - first.t < 30) return { power: null, speed: null };
  const hours = (last.t - first.t) / 3600;
  const miles = last.distance - first.distance;
  return {
    power: (last.wh - first.wh) / hours,
    speed: Number.isFinite(miles) && miles >= 0 ? miles / hours : null,
  };
}

function percentile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(fraction * sorted.length))];
}

// The car sends its latest battery estimate in every packet, and it changes when the car
// finishes a new 30 second window. Two low estimates in a row trigger the warning
function updateBattery(batt, data) {
  const voc = toNum(data.restVoltage);
  const r = toNum(data.resistance);
  if (!Number.isFinite(voc) || !Number.isFinite(r) || (voc === batt.voc && r === batt.r)) return;
  batt.voc = voc;
  batt.r = r;
  const low = voc < VOC_WARNING || r > R_WARNING;
  batt.lowCount = low ? batt.lowCount + 1 : 0;
}

function batteryStatus(batt) {
  if (batt.lowCount >= 2) return { text: "Collapse warning", short: "Battery low", tone: "red" };
  if (batt.lowCount === 1) return { text: "Watch", short: "Battery watch", tone: "amber" };
  if (batt.voc != null) return { text: "Healthy", short: "Battery OK", tone: "green" };
  return { text: "Estimating…", short: "Battery —", tone: "gray" }; // short is for the pit board
}

function startLap(car, t, complete) {
  return {
    startT: t,
    startWh: car.wh,
    startDistance: car.distance,
    powerAllowed: allowedPower(car, t),
    currents: [],
    points: [],
    complete,
  };
}

function finishLap(car, t) {
  const lap = car.lap;
  const seconds = t - lap.startT;
  const wh = lap.startWh != null && car.wh != null ? car.wh - lap.startWh : null;
  const miles = lap.startDistance != null && car.distance != null ? car.distance - lap.startDistance : null;
  car.laps.push({
    number: car.lapCount + 1,
    startT: lap.startT,
    startWh: lap.startWh,
    startDistance: lap.startDistance,
    powerAllowed: lap.powerAllowed,
    seconds,
    wh,
    miles,
    whAllowed: lap.powerAllowed != null ? lap.powerAllowed * seconds / 3600 : null,
    peakCurrent: percentile(lap.currents, 0.98),
    complete: lap.complete && wh != null,
    points: lap.points,
  });

  // Only the last and most efficient laps keep their map points
  const best = bestLap(car);
  car.laps.forEach((rec, index) => {
    if (rec !== best && index !== car.laps.length - 1) rec.points = null;
  });
}

// This finds the most efficient lap from what the client can remember
function bestLap(car) {
  let best = null;
  for (const lap of car.laps) {
    if (lap.complete && (best == null || lap.wh < best.wh)) best = lap;
  }
  return best;
}

// Typical lap length in miles, the median of the last few complete laps
function lapMiles(car) {
  const miles = car.laps
    .filter((lap) => lap.complete && lap.miles > 0)
    .slice(-LAP_LENGTH_LAPS)
    .map((lap) => lap.miles)
    .sort((a, b) => a - b); // This is all one line!
  return miles.length ? miles[Math.floor(miles.length / 2)] : null; // Return the middle one
}

// Follow the lap count from the timing events
function updateLaps(carId, laps) {
  if (laps == null) return;
  const car = carState(carId);
  const t = raceSecondsNow() ?? 0;

  if (car.lapCount == null || car.lap == null) {
    // Only a lap watched from its start has trustworthy totals
    car.lapCount = laps;
    car.lap = startLap(car, t, laps === 0 && t < 5);
    return;
  }

  if (laps === car.lapCount) return;

  if (laps === car.lapCount + 1) {
    finishLap(car, t);
    car.lap = startLap(car, t, true);
  } else if (laps === car.lapCount - 1 && car.laps.length && car.laps.at(-1).number === car.lapCount) {
    // Lap- undoes the last lap mark, so join that lap back onto the current one
    const undone = car.laps.pop();
    car.lap = {
      startT: undone.startT,
      startWh: undone.startWh,
      startDistance: undone.startDistance,
      powerAllowed: undone.powerAllowed,
      currents: car.lap.currents,
      points: (undone.points ?? []).concat(car.lap.points),
      complete: undone.complete && car.lap.complete,
    };
  } else {
    car.lap = startLap(car, t, false);
  }

  car.lapCount = laps;
  drawLapChart(carId);
  saveMetrics();
}

function updateMetrics(carId, data) {
  const car = carState(carId);
  const t = raceSecondsNow();
  // Race time stops while paused, so only collect history while the race is running
  const running = race.status === "Running" && t != null;
  const wh = toNum(data.wattHrs);
  const ah = toNum(data.ampHrs);
  const current = toNum(data.current);
  const distance = toNum(data.distance);

  if (Number.isFinite(distance)) {
    car.distance = distance;
    if (car.lap && car.lap.startDistance == null) car.lap.startDistance = distance;
  }

  // Energy totals come from the car (watt hours are integrated on the car)
  car.ampHrs = Number.isFinite(ah) ? ah : null;
  if (Number.isFinite(wh)) {
    car.wh = wh;
    // The lap in progress started before we knew the energy
    if (car.lap && car.lap.startWh == null) car.lap.startWh = wh;
  }

  if (running && car.wh != null) {
    car.recent.push({ t, wh: car.wh, distance });
    while (car.recent.length && car.recent[0].t < t - RECENT_SECONDS) car.recent.shift();
  }

  updateBattery(car.batt, data);

  const x = toNum(data.gpsX);
  const y = toNum(data.gpsY);
  const hasPosition = data.fix === true && Number.isFinite(x) && Number.isFinite(y);
  if (hasPosition) {
    car.track.push([x, y]);
    if (car.track.length > TRACK_POINTS) car.track.shift();
    car.trail.push([x, y, Number.isFinite(current) ? current : 0]);
    if (car.trail.length > TRAIL_POINTS) car.trail.shift();
  }

  if (running && car.lap) {
    if (Number.isFinite(current)) car.lap.currents.push(current);
    if (hasPosition) car.lap.points.push([x, y, Number.isFinite(current) ? current : 0]);
  }
}

function budgetTone(percent) {
  return percent > 105 ? "red" : percent > 100 ? "amber" : "green";
}

function renderMetrics(carId) {
  const car = carState(carId);
  const t = raceSecondsNow();
  const active = raceActive() && t != null;
  const ready = active && t >= MIN_PROJECTION_SECONDS;

  // Linear projections of energy and amp hours to the end of the race
  const projWh = ready && car.wh != null ? car.wh / t * RACE_SECONDS : null;
  const projPct = projWh != null ? projWh / BUDGET_WH * 100 : null;
  setNum(carId + "projWh", projWh, 0);
  setNum(carId + "projWhPct", projPct, 0);
  setNum(carId + "pitEnergy", projPct, 0);
  setWidth(carId + "projWhBar", projPct / PROJECTION_MAX * 100);
  const projTone = projPct == null ? null : budgetTone(projPct);
  setTone(document.getElementById(carId + "projWhBar"), BG_TONES, projTone ?? "green");
  setTone(document.getElementById(carId + "pitEnergy"), TEXT_TONES, projTone);
  setTone(document.getElementById(carId + "projWhPct"), TEXT_TONES, projTone);

  const projAh = ready && car.ampHrs != null ? car.ampHrs / t * RACE_SECONDS : null;
  const ahPct = projAh != null ? projAh / BUDGET_AH * 100 : NaN;
  setNum(carId + "estEndAmpHrs", projAh, 2);
  setWidth(carId + "projAhBar", ahPct / PROJECTION_MAX * 100);
  setTone(document.getElementById(carId + "projAhBar"), BG_TONES, budgetTone(ahPct));

  // Power and speed vs. what the budget allows
  const rates = active ? recentRates(car) : { power: null, speed: null };
  const allowed = active ? allowedPower(car, t) : null;
  const target = targetSpeed(allowed);
  setNum(carId + "powerRecent", rates.power, 0);
  setNum(carId + "powerAllowed", allowed, 0);
  setWidth(carId + "powerBar", rates.power / POWER_MAX * 100);
  const powerMark = document.getElementById(carId + "powerMark");
  if (powerMark) {
    powerMark.style.left = clamp((allowed ?? 0) / POWER_MAX * 100, 0, 100) + "%";
    powerMark.hidden = allowed == null;
  }
  setTone(document.getElementById(carId + "powerBar"), BG_TONES,
    rates.power != null && allowed != null && rates.power > allowed * 1.05 ? "red" : "green");

  // Update the speed target
  setNum(carId + "targetSpeed", target, 1);
  const miles = lapMiles(car);
  setText(carId + "targetLapTime", target > 0 && miles != null ? formatLapTime(miles / target * 3600) : "—");
  setNum(carId + "targetSpeedGauge", target, 1);
  setNum(carId + "recentSpeed", rates.speed, 1);
  updateSpeedTarget(carId, target); // Update the visual

  if (!active) {
    setPill(carId + "paceAdvice", "Waiting for race", "gray");
  } else if (target == null || rates.speed == null) {
    setPill(carId + "paceAdvice", "Measuring pace…", "gray");
  } else {
    const diff = rates.speed - target;
    if (Math.abs(diff) < ON_PACE_MPH) setPill(carId + "paceAdvice", "On pace", "green");
    else if (diff > 0) setPill(carId + "paceAdvice", `Ease off ${diff.toFixed(1)} mph`, diff > 2 ? "red" : "amber");
    else setPill(carId + "paceAdvice", `Room to push ${(-diff).toFixed(1)} mph`, "green");
  }

  // Update the battery waring on the page
  const status = batteryStatus(car.batt);
  setText(carId + "battStatus", status.text);
  setTone(document.getElementById(carId + "battStatus"), TEXT_TONES, status.tone);
  setPill(carId + "pitBattery", status.short, status.tone);
}
