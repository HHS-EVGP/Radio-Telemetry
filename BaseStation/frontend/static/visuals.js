//// Gauges ////
const SPEED_START_ANGLE = 150; // Degrees, clockwise from the right, matching the arc in dashboard.html
const SPEED_SWEEP = 240; // How far to sweep the speed gauge around

function polar(radius, angle) {
  const rad = angle * Math.PI / 180;
  return [100 + radius * Math.cos(rad), 100 + radius * Math.sin(rad)];
}

function buildSpeedTicks() {
  document.querySelectorAll("[id$='speedTicks']").forEach((group) => {
    let svg = "";
    // A tick every 5 mph, longer every 10
    for (let mph = 0; mph <= SPEED_MAX; mph += 5) {
      const angle = SPEED_START_ANGLE + SPEED_SWEEP * mph / SPEED_MAX;
      const [x1, y1] = polar(91, angle);
      const [x2, y2] = polar(mph % 10 === 0 ? 99 : 95, angle);
      svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke-width="3" />`;
    }
    group.innerHTML = svg;
  });
}

function updateSpeedTarget(carId, target) {
  const marker = document.getElementById(carId + "speedTarget");
  if (!marker) return;
  if (target == null) {
    marker.setAttribute("visibility", "hidden");
    return;
  }
  const angle = SPEED_START_ANGLE + SPEED_SWEEP * clamp(target / SPEED_MAX, 0, 1);
  marker.setAttribute("transform", `rotate(${angle} 100 100)`);
  marker.setAttribute("visibility", "visible");
}

function updateGauges(carId, data) {
  const speed = toNum(data.speed);
  const arc = document.getElementById(carId + "speedArc");
  if (arc) arc.setAttribute("stroke-dasharray", `${Number.isFinite(speed) ? clamp(speed / SPEED_MAX * 100, 0, 100) : 0} 100`);
  setNum(carId + "pitSpeed", speed, 1);

  const throttle = toNum(data.throttle) / PEDAL_SCALE;
  const brake = toNum(data.brake) / PEDAL_SCALE;
  const throttleBar = document.getElementById(carId + "throttleBar");
  if (throttleBar) throttleBar.style.height = (Number.isFinite(throttle) ? clamp(throttle, 0, 100) : 0) + "%";
  const brakeBar = document.getElementById(carId + "brakeBar");
  if (brakeBar) brakeBar.style.height = (Number.isFinite(brake) ? clamp(brake, 0, 100) : 0) + "%";

  const voltage = toNum(data.voltage);
  const current = toNum(data.current);
  setNum(carId + "power", voltage * current, 0);

  // The analysis found the motor still drawing current while the mechanical brake was on
  const brakeWarn = document.getElementById(carId + "brakeWarn");
  if (brakeWarn) brakeWarn.hidden = !(brake > BRAKE_ON && current > CURRENT_ON);

  TEMP_FIELDS.forEach((field) => {
    const temp = toNum(data[field]);
    const bar = document.getElementById(carId + field + "Bar");
    const value = document.getElementById(carId + field);
    const tone = temp > HOT_TEMP ? "red" : temp > WARM_TEMP ? "amber" : "green";
    setWidth(carId + field + "Bar", temp / TEMP_MAX * 100);
    setTone(bar, BG_TONES, tone);
    setTone(value, TEXT_TONES, temp > HOT_TEMP ? "red" : null);
  });

  const roll = toNum(data.roll);
  const pitch = toNum(data.pitch);
  const horizon = document.getElementById(carId + "horizon");
  if (horizon) {
    horizon.setAttribute("transform",
      `rotate(${Number.isFinite(roll) ? -roll : 0}) translate(0 ${Number.isFinite(pitch) ? clamp(pitch, -45, 45) : 0})`);
  }

  const heading = toNum(data.heading);
  const rose = document.getElementById(carId + "compassRose");
  if (rose) {
    const angle = Number.isFinite(heading) ? heading : 0;
    rose.setAttribute("transform", `rotate(${-angle})`);
    // Keep the letters upright as the rose turns
    rose.querySelectorAll("text").forEach((letter) => {
      const x = letter.getAttribute("x") ?? 0;
      const y = letter.getAttribute("y") ?? 0;
      letter.setAttribute("transform", `rotate(${angle} ${x} ${y})`);
    });
  }
}


//// Lap energy chart ////
function drawLapChart(carId) {
  const svg = document.getElementById(carId + "lapChart");
  if (!svg) return;
  const car = carState(carId);
  const laps = car.laps.slice(-CHART_LAPS);

  const formatLap = (lap) => lap
    ? `#${lap.number} · ${lap.wh != null ? lap.wh.toFixed(1) + " Wh" : "—"} · ${formatClock(lap.seconds)}`
    : "—";
  setText(carId + "lastLapEnergy", formatLap(car.laps.at(-1)));
  setText(carId + "bestLapEnergy", formatLap(bestLap(car)));

  if (!laps.length) {
    svg.innerHTML = `<text x="160" y="75" text-anchor="middle" fill="currentColor" font-size="11">Lap energy appears after the first lap</text>`;
    return;
  }

  const width = 320, height = 150, left = 30, right = 30, top = 8, bottom = 20;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const maxWh = Math.max(1, ...laps.map((lap) => Math.max(lap.wh ?? 0, lap.whAllowed ?? 0))) * 1.15;
  const maxA = Math.max(50, ...laps.map((lap) => lap.peakCurrent ?? 0));
  const slot = plotW / Math.max(laps.length, 6);
  const barW = slot * 0.6;
  const yWh = (wh) => top + plotH - wh / maxWh * plotH;
  const yA = (amps) => top + plotH - amps / maxA * plotH;

  let out = "";
  for (const fraction of [0, 0.5, 1]) {
    const y = top + plotH - fraction * plotH;
    out += `<line x1="${left}" x2="${width - right}" y1="${y}" y2="${y}" stroke="var(--chart-grid)" />`;
    out += `<text x="${left - 4}" y="${y}" text-anchor="end" dominant-baseline="middle" fill="currentColor" font-size="9">${Math.round(maxWh * fraction)}</text>`;
    out += `<text x="${width - right + 4}" y="${y}" dominant-baseline="middle" fill="currentColor" font-size="9">${Math.round(maxA * fraction)}</text>`;
  }
  out += `<text x="2" y="${top + plotH / 2}" fill="currentColor" font-size="9" transform="rotate(-90 6 ${top + plotH / 2})" text-anchor="middle">Wh</text>`;
  out += `<text x="${width - 4}" y="${top + plotH / 2}" fill="currentColor" font-size="9" text-anchor="middle">A</text>`;

  const peaks = [];
  laps.forEach((lap, index) => {
    const cx = left + slot * (index + 0.5);
    const over = lap.wh != null && lap.whAllowed != null && lap.wh > lap.whAllowed;
    const fill = !lap.complete ? "fill-slate-400 dark:fill-slate-600" : over ? "fill-red-500" : "fill-emerald-500";
    const title = `Lap ${lap.number}: ${lap.wh?.toFixed(1) ?? "—"} Wh used, ${lap.whAllowed?.toFixed(1) ?? "—"} Wh allowed, ` +
      `${formatClock(lap.seconds)}, peak ${lap.peakCurrent?.toFixed(0) ?? "—"} A${lap.complete ? "" : " (partial)"}`;

    out += `<g><title>${title}</title>`;
    if (lap.wh != null) {
      const y = yWh(Math.max(0, lap.wh));
      out += `<rect x="${cx - barW / 2}" y="${y}" width="${barW}" height="${top + plotH - y}" rx="2" class="${fill}" />`;
    }
    if (lap.whAllowed != null) {
      const y = yWh(lap.whAllowed);
      out += `<line x1="${cx - slot * 0.42}" x2="${cx + slot * 0.42}" y1="${y}" y2="${y}" stroke-width="2" class="stroke-slate-900 dark:stroke-white" />`;
    }
    out += `</g>`;
    out += `<text x="${cx}" y="${height - 6}" text-anchor="middle" fill="currentColor" font-size="9">${lap.number}</text>`;
    if (lap.peakCurrent != null) peaks.push([cx, yA(lap.peakCurrent), lap.peakCurrent]);
  });

  if (peaks.length > 1) {
    out += `<polyline points="${peaks.map(([x, y]) => `${x},${y}`).join(" ")}" fill="none" stroke-width="1.5" class="stroke-amber-500" />`;
  }
  for (const [x, y, amps] of peaks) {
    const tone = amps > PEAK_CURRENT_HIGH ? "fill-red-500" : amps > PEAK_CURRENT_OK ? "fill-amber-500" : "fill-emerald-500";
    out += `<circle cx="${x}" cy="${y}" r="3.5" stroke-width="1.5" class="${tone} stroke-white dark:stroke-slate-900" />`;
  }

  svg.innerHTML = out;
}


//// Track map ////
function currentColor(amps) {
  if (amps < 0) {
    // Regen: green fading into blue
    const fraction = clamp(amps / MAP_CURRENT_MIN, 0, 1);
    return `hsl(${140 + 80 * fraction} ${70 + 10 * fraction}% ${45 + 7 * fraction}%)`;
  }
  // Green through yellow to red
  const fraction = clamp(amps / MAP_CURRENT_MAX, 0, 1);
  return `hsl(${140 - 140 * fraction} ${70 + 10 * fraction}% ${45 + 5 * Math.sin(fraction * Math.PI)}%)`;
}

// Draw the map legends from currentColor so they always match the map
function buildCurrentLegends() {
  const range = MAP_CURRENT_MAX - MAP_CURRENT_MIN;
  const stops = [];
  for (let amps = MAP_CURRENT_MIN; amps <= MAP_CURRENT_MAX; amps += 5) {
    stops.push(`${currentColor(amps)} ${(amps - MAP_CURRENT_MIN) / range * 100}%`);
  }
  document.querySelectorAll(".current-legend").forEach((bar) => {
    bar.style.background = `linear-gradient(to right, ${stops.join(", ")})`;
  });
  document.querySelectorAll(".current-legend-zero").forEach((label) => {
    label.style.left = -MAP_CURRENT_MIN / range * 100 + "%";
  });
}

function mapPoints(car) {
  if (car.mapMode === "last") return car.laps.at(-1)?.points ?? [];
  if (car.mapMode === "best") return bestLap(car)?.points ?? [];
  return raceActive() && car.lap?.points.length ? car.lap.points : car.trail;
}

// Fit the points in the canvas with the same scale on both axes.
// Returns converters between GPS meters and canvas pixels
function fitMapView(points, width, height) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [x, y] of points) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  const pad = 16;
  const scale = Math.min((width - 2 * pad) / Math.max(maxX - minX, 1), (height - 2 * pad) / Math.max(maxY - minY, 1));
  const offsetX = (width - (maxX - minX) * scale) / 2;
  const offsetY = (height - (maxY - minY) * scale) / 2;
  // GPS Y points north, the canvas Y points down
  return {
    width,
    height,
    toCanvas: (x, y) => [offsetX + (x - minX) * scale, height - offsetY - (y - minY) * scale],
    toGps: (cx, cy) => [minX + (cx - offsetX) / scale, minY + (height - offsetY - cy) / scale],
  };
}

function drawMap(carId) {
  const canvas = document.getElementById(carId + "map");
  if (!canvas || !canvas.clientWidth) return;
  const car = carState(carId);

  // Draw at the screen's real pixel density so lines stay sharp
  const ratio = window.devicePixelRatio || 1; // || is like the ?? operator, but it also throws out 0
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const points = mapPoints(car);
  const all = car.track.concat(points);
  if (!all.length) {
    ctx.fillStyle = cssVar("--chart-text");
    ctx.font = "13px system-ui, sans-serif";
    ctx.textAlign = "center";
    const message = car.mapMode === "live" ? "Waiting for a GPS fix" : "No lap recorded yet";
    ctx.fillText(message, width / 2, height / 2);
    return;
  }

  // The auto lap line is part of the fit so it can't end up off the map.
  // Hold the view still while the line is dragged, so the line stays under the pointer
  const line = car.autoLap.enabled ? car.autoLap.line ?? [] : [];
  if (!car.mapDrag || !car.mapView) car.mapView = fitMapView(all.concat(line), width, height);
  const { toCanvas } = car.mapView;
  if (car.autoLap.enabled && !car.autoLap.line) {
    car.autoLap.line = defaultAutoLapLine(car.mapView);
    if (autoLapSync) syncAutoLapLines(carId);
  }

  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  if (car.track.length > 1) {
    ctx.strokeStyle = cssVar("--chart-track");
    ctx.lineWidth = 8;
    ctx.beginPath();
    car.track.forEach(([x, y], index) => {
      const [cx, cy] = toCanvas(x, y);
      if (index === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });
    ctx.stroke();
  }

  ctx.lineWidth = 4;
  for (let index = 1; index < points.length; index++) {
    const [x1, y1] = toCanvas(points[index - 1][0], points[index - 1][1]);
    const [x2, y2] = toCanvas(points[index][0], points[index][1]);
    ctx.strokeStyle = currentColor(points[index][2]);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  if (car.autoLap.enabled && car.autoLap.line) drawAutoLapLine(ctx, car.autoLap.line.map(([x, y]) => toCanvas(x, y)));

  if (car.mapMode !== "live") return;

  // Show where both cars are, with this car on top
  const carIds = Object.keys(cars).filter((id) => id !== carId).concat(carId);
  for (const id of carIds) {
    const position = carState(id).trail.at(-1);
    if (!position) continue;
    const [cx, cy] = toCanvas(position[0], position[1]);
    // Each car's map sits inside its accent class, which sets --car
    ctx.fillStyle = getComputedStyle(document.getElementById(id + "map") ?? canvas).getPropertyValue("--car");
    ctx.strokeStyle = id === carId ? "white" : cssVar("--chart-grid");
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(cx, cy, id === carId ? 7 : 5, 0, 2 * Math.PI);
    ctx.fill();
    ctx.stroke();
  }
}

function drawAllMaps() {
  Object.keys(cars).forEach(drawMap);
}

function setMapMode(carId, mode) {
  carState(carId).mapMode = mode;
  document.querySelectorAll(`[data-car="${carId}"][data-map-mode]`).forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.mapMode === mode));
  });
  drawMap(carId);
}


//// Auto lap line ////
const LINE_HANDLE_RADIUS = 7; // px, the dots on the ends of the line
const LINE_HIT_SLOP = 14; // px, how close a press has to be to grab the line or a handle
const LINE_MIN_HALF = 5; // m, half the length of a new line at least, in case the map only has a few points

// A new line starts in the middle of the map, which is usually the infield, so it can't mark a lap
// until it's dragged onto the track
function defaultAutoLapLine(view) {
  const [cx, cy] = view.toGps(view.width / 2, view.height / 2);
  const half = Math.max(view.toGps(view.width * 0.65, 0)[0] - cx, LINE_MIN_HALF);
  return [[cx - half, cy], [cx + half, cy]];
}

// Drawn as a checkered line with a handle on each end. ends are canvas [x, y] points
function drawAutoLapLine(ctx, ends) {
  const [[x1, y1], [x2, y2]] = ends;
  ctx.lineCap = "butt";
  ctx.lineWidth = 6;
  ctx.strokeStyle = "white";
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.strokeStyle = "#0f172a";
  ctx.setLineDash([6, 6]);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.lineCap = "round";

  ctx.fillStyle = "white";
  ctx.strokeStyle = "#0f172a";
  ctx.lineWidth = 2;
  for (const [x, y] of ends) {
    ctx.beginPath();
    ctx.arc(x, y, LINE_HANDLE_RADIUS, 0, 2 * Math.PI);
    ctx.fill();
    ctx.stroke();
  }
}

function distanceToSegment([px, py], [x1, y1], [x2, y2]) {
  const dx = x2 - x1, dy = y2 - y1;
  const fraction = dx || dy ? clamp(((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy), 0, 1) : 0;
  return Math.hypot(px - (x1 + fraction * dx), py - (y1 + fraction * dy));
}

// What part of the auto lap line is at a canvas point: 0 or 1 for an end, "line" for the middle, or null
function autoLapLineHit(carId, point) {
  const car = carState(carId);
  if (!car.autoLap.enabled || !car.autoLap.line || !car.mapView) return null;
  const ends = car.autoLap.line.map(([x, y]) => car.mapView.toCanvas(x, y));
  for (const index of [0, 1]) {
    if (Math.hypot(point[0] - ends[index][0], point[1] - ends[index][1]) <= LINE_HIT_SLOP) return index;
  }
  return distanceToSegment(point, ends[0], ends[1]) <= LINE_HIT_SLOP ? "line" : null;
}

// Drag the middle of the line to move it, or an end to resize and turn it
function setupAutoLapDragging(carId) {
  const canvas = document.getElementById(carId + "map");
  if (!canvas) return;
  const car = carState(carId);
  // Pointer position in canvas pixels, kept inside the canvas so the line can't be lost off the edge
  const canvasPoint = (event) => {
    const rect = canvas.getBoundingClientRect();
    return [clamp(event.clientX - rect.left, 0, rect.width), clamp(event.clientY - rect.top, 0, rect.height)];
  };

  canvas.addEventListener("pointerdown", (event) => {
    const point = canvasPoint(event);
    const hit = autoLapLineHit(carId, point);
    if (hit == null) return;
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    car.mapDrag = { hit, start: car.mapView.toGps(...point), line: car.autoLap.line.map((end) => [...end]) };
    canvas.style.cursor = "grabbing";
  });

  canvas.addEventListener("pointermove", (event) => {
    const point = canvasPoint(event);
    const drag = car.mapDrag;
    if (!drag) {
      const hit = autoLapLineHit(carId, point);
      canvas.style.cursor = hit === "line" ? "grab" : hit != null ? "move" : "";
      return;
    }
    const [x, y] = car.mapView.toGps(...point);
    if (drag.hit === "line") {
      const dx = x - drag.start[0], dy = y - drag.start[1];
      car.autoLap.line = drag.line.map(([lx, ly]) => [lx + dx, ly + dy]);
    } else {
      car.autoLap.line[drag.hit] = [x, y];
    }
    if (autoLapSync) {
      syncAutoLapLines(carId);
      drawAllMaps();
    } else {
      drawMap(carId);
    }
  });

  const endDrag = () => {
    if (!car.mapDrag) return;
    car.mapDrag = null;
    canvas.style.cursor = "";
    saveAutoLap();
    drawMap(carId);
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);

  // On touch screens, only stop the page from scrolling when the touch grabs the line
  canvas.addEventListener("touchstart", (event) => {
    const rect = canvas.getBoundingClientRect();
    const touch = event.touches[0];
    if (autoLapLineHit(carId, [touch.clientX - rect.left, touch.clientY - rect.top]) != null) event.preventDefault();
  }, { passive: false });
}

// Turn auto lapping on or off for a car. The manual lap buttons stay visible but are disabled while it's on
function setAutoLap(carId, enabled) {
  const car = carState(carId);
  car.autoLap.enabled = enabled;
  if (enabled && autoLapSync) syncAutoLapLines(carId);
  document.querySelectorAll(`[data-auto-lap="${carId}"]`).forEach((toggle) => { toggle.checked = enabled; });
  document.querySelectorAll(`[data-lap-button="${carId}"]`).forEach((button) => { button.disabled = enabled; });
  const lapControls = document.getElementById(carId + "lapControls");
  if (lapControls) lapControls.title = enabled ? "Turn off automatic lapping to use the lap buttons" : "";
  // The sync checkbox only shows next to a map whose line is showing
  const syncRow = document.getElementById(carId + "autoLapSyncRow");
  if (syncRow) syncRow.hidden = !enabled;
  drawMap(carId);
}

// Turn line syncing on or off. carId is the car whose line the others jump to
function setAutoLapSync(sync, carId) {
  autoLapSync = sync;
  document.querySelectorAll("[data-auto-lap-sync]").forEach((checkbox) => { checkbox.checked = sync; });
  if (sync && carId) syncAutoLapLines(carId);
  drawAllMaps();
}

function flashLapButton(carId) {
  const button = document.getElementById(carId + "lapPlus");
  if (!button) return;
  button.classList.remove("lap-flash");
  void button.offsetWidth; // Reading the layout restarts the animation if it's already flashing
  button.classList.add("lap-flash");
}
