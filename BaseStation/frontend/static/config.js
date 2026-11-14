// Race strategy settings, from the 2025-26 race data analysis
const RACE_SECONDS = 3600;
const BUDGET_WH = 590; // Both 2026 races had the battery voltage collapse at about 590 Wh / 13 Ah
const BUDGET_AH = 13;
const WH_PER_MILE_SLOPE = 1.87; // Clean laps: Wh per mile = 1.87 * mph - 1.6
const WH_PER_MILE_INTERCEPT = -1.6;
const RECENT_SECONDS = 120; // Window for "last 2 minutes" power and speed
const MIN_PROJECTION_SECONDS = 30; // Period to not give projections because they are too noisy
const ON_PACE_MPH = 0.5; // Speed difference from the target that still counts as on pace

// Battery collapse warning (gave 7-10 minutes warning in both 2026 races)
// The car estimates restVoltage and resistance from the voltage sag under load every 30 seconds
const VOC_WARNING = 47.5; // Volts, estimated open circuit voltage
const R_WARNING = 0.14; // Ohms, estimated pack + wiring resistance

// Display ranges
const SPEED_MAX = 35; // mph, end of the speedometer
const POWER_MAX = 1500; // W, end of the power meter
const PROJECTION_MAX = 150; // Percent of budget at the end of the projection meters
const PEDAL_SCALE = 10; // The car sends pedals as 0 to 1000, this makes them a percent
const TEMP_MAX = 80; // °C, end of the temperature bars
const HOT_TEMP = 50; // °C, temperatures above this turn red
const WARM_TEMP = 40;
const DISCONNECTED_TEMP = -50; // Unplugged thermistors read about -273
const PEAK_CURRENT_OK = 30; // A, lap peak currents (98th percentile) above these are harsh on the battery
const PEAK_CURRENT_HIGH = 40;
const MAP_CURRENT_MAX = 40; // A, red end of the map colors
const MAP_CURRENT_MIN = -25; // A, blue end of the map colors (regen, the most regen historically has been -18 A)
const BRAKE_ON = 5; // Percent of brake that counts as braking
const CURRENT_ON = 5; // A drawn while braking that counts as "braking under power"
const STALE_SECONDS = 3; // Seconds without a packet before a car shows as stale
const OFFLINE_SECONDS = 30;
const TRACK_POINTS = 3000; // GPS points kept for the map outline
const TRAIL_POINTS = 150; // GPS points shown on the live map when no race is running
const CHART_LAPS = 15; // Laps shown in the lap energy chart
const LAP_LENGTH_LAPS = 5; // Recent complete laps used to measure the lap length for the target lap time
const STORAGE_KEY = "evgpRaceMetrics"; // key for client cache

// Numeric telemetry fields and their decimal places. Each one is shown in the element with id <carId><field>
const NUMERIC_FIELDS = {
  throttle: 0, brake: 0,
  ambientTemp: 1, motorTemp: 1, batt1: 1, batt2: 1, batt3: 1, batt4: 1,
  ampHrs: 2, voltage: 1, current: 1, speed: 1, distance: 2,
  wattHrs: 0, restVoltage: 2, resistance: 3,
  roll: 1, pitch: 1, heading: 0, altitude: 1,
  gpsX: 1, gpsY: 1,
};

const TEMP_FIELDS = ["motorTemp", "batt1", "batt2", "batt3", "batt4", "ambientTemp"];

// Helper to set text content if element exists
function setText(id, text) {
  const elem = document.getElementById(id);
  if (elem) {
    elem.textContent = text ?? "—";
  }
}

// Helper to show a number with a fixed number of decimals, or a dash if it's missing
function setNum(id, num, decimals = 1) {
  const elem = document.getElementById(id);
  if (!elem) return;
  // null/undefined (missing or NAN on the car) parse to NaN
  const parsed = parseFloat(num);
  elem.textContent = Number.isFinite(parsed) ? parsed.toFixed(decimals) : "—";
}

function toNum(value) {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : NaN;
}

// Clamp returns the value to the range (min, max)
function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function setWidth(id, percent) {
  const elem = document.getElementById(id);
  if (elem) elem.style.width = (Number.isFinite(percent) ? clamp(percent, 0, 100) : 0) + "%";
}

// Swap one of a set of classes on an element, like the pill colors
function setTone(elem, tones, tone) {
  if (!elem) return;
  elem.classList.remove(...Object.values(tones));
  if (tones[tone]) elem.classList.add(tones[tone]);
}

const PILL_TONES = { gray: "pill-gray", green: "pill-green", amber: "pill-amber", red: "pill-red" };
const TEXT_TONES = { green: "text-good", amber: "text-warn", red: "text-bad" };
const BG_TONES = { green: "bg-good", amber: "bg-warn", red: "bg-bad" };

function setPill(id, text, tone) {
  const elem = document.getElementById(id);
  if (!elem) return;
  elem.textContent = text;
  setTone(elem, PILL_TONES, tone);
}

function formatClock(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// Same m:ss.t format as the server's lap times
function formatLapTime(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  const tenths = Math.floor(Math.max(0, seconds) * 10);
  const minutes = Math.floor(tenths / 600);
  const rest = tenths % 600;
  return `${minutes}:${String(Math.floor(rest / 10)).padStart(2, "0")}.${rest % 10}`;
}

// Function for extracting values form the stylesheet, so that canvases can match the theme
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
