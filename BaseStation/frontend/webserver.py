from flask import Flask, render_template, jsonify, request
from datetime import datetime
import time
import threading
import sqlite3
import pickle
import uuid
import os
import redis
import json

from flask_sse import sse

app = Flask(__name__)

# Configure Redis backend for Flask-SSE
# Telemetry events are triggered by station.py, timing events by this file
app.config["REDIS_URL"] = "redis://localhost:6379/0"
app.register_blueprint(sse, url_prefix='/stream')

redis_client = redis.Redis(host='localhost', port=6379, db=0)

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DB_PATH = os.path.join(REPO_ROOT, "BaseStation", "EVGPTelemetry.sqlite")
RACEINFO_PATH = os.path.join(REPO_ROOT, "raceInfo.pkl")

CARS = ["blue_445", "red_111"]  # Also the database table names (keep in sync with station.py)
TIMING_INTERVAL = 0.2  # Seconds between timing broadcasts
TELEMETRY_FRESHNESS = 5  # Seconds a car's last timestamp is trusted for lap boundaries

# gunicorn runs several workers, so race state lives in the pickle file (shared and
# crash-safe), changes are serialized with a Redis lock, and only one worker
# (the "leader") broadcasts timing events
STATE_LOCK = "race_state_lock"
LEADER_KEY = "timing_leader"
WORKER_ID = uuid.uuid4().hex.encode()

# Race and lap controls require this access code. Authenticated client IPs are
# kept in Redis so every gunicorn worker sees them
AUTH_CODE = "hhsevgp"  # Make this whatever you like
AUTHED_USERS_KEY = "authed_users"

# Clear the authenticated clients when the server restarts. Every gunicorn worker
# runs this, but they share a parent process (the gunicorn master), so only the
# first worker of a new server clears the list. A worker that gunicorn replaces
# mid race has the same parent and leaves the list alone
SERVER_KEY = "server_id"
server_id = f"{os.getppid()}"
if redis_client.set(SERVER_KEY, server_id, get=True) != server_id.encode():
    redis_client.delete(AUTHED_USERS_KEY)

# Latest telemetry seen per car: {car_id: {"timestamp", "received"}}
latest_telemetry = {}


## Race state persistence ##
# State is None when no race has been started, otherwise:
# {
#   "started_at": server time the race started,
#   "ended_at": server time the race was stopped, or None,
#   "paused_at": server time the race was paused, or None,
#   "paused_total": total seconds spent paused,
#   "cars": {car_id: {
#       "start_ts": car timestamp when the race started,
#       "laps": [{"race_time": race time at the lap, "car_ts": car timestamp at the lap}]
#   }}
# }
def load_state():
    if not os.path.exists(RACEINFO_PATH):
        return None
    try:
        with open(RACEINFO_PATH, "rb") as file:
            return pickle.load(file)
    except Exception as e:
        print("Error unpickling race data:", e)
        return None


def save_state(state):
    # Write to a temp file then swap it in so a crash never leaves a half written file
    tmp_path = RACEINFO_PATH + ".tmp"
    with open(tmp_path, "wb") as file:
        pickle.dump(state, file)
    os.replace(tmp_path, RACEINFO_PATH)


## Timing helpers ##
def race_status(state):
    if state is None:
        return "Not Started"
    if state["ended_at"] is not None:
        return "Finished"
    if state["paused_at"] is not None:
        return "Paused"
    return "Running"


def race_elapsed(state, now):
    end = state["ended_at"] or state["paused_at"] or now
    return max(0.0, end - state["started_at"] - state["paused_total"])


def format_time(seconds):
    if seconds is None:
        return None
    tenths = int(seconds * 10)
    minutes, tenths = divmod(tenths, 600)
    return f"{minutes}:{tenths // 10:02d}.{tenths % 10}"


def car_timestamp(car_id):
    # Use the car's own clock when possible so lap boundaries line up with the
    # timestamps stored in the database. Fall back to server time if the car is quiet
    car = latest_telemetry.get(car_id)
    if car and car["timestamp"] is not None and time.time() - car["received"] < TELEMETRY_FRESHNESS:
        return car["timestamp"]
    else:
        return time.time()


def build_timing(state):
    now = time.time()
    status = race_status(state)
    elapsed = race_elapsed(state, now) if state else None

    timing = {
        "sysTime": datetime.now().strftime("%H:%M:%S"),
        "status": status,
        "raceTime": format_time(elapsed),
        "raceSeconds": elapsed,  # Unformatted race time, used by the dashboard's pace metrics
        "raceStartedAt": state["started_at"] if state else None,  # Identifies the race
        "cars": {},
    }

    for car_id in CARS:
        car_info = {
            "laps": None,
            "lapTime": None,
            "lastLapTime": None,
            "fastestLapTime": None,
        }

        if state is not None:
            lap_marks = [lap["race_time"] for lap in state["cars"][car_id]["laps"]]
            lap_times = [b - a for a, b in zip([0.0] + lap_marks, lap_marks)]

            car_info["laps"] = len(lap_marks)
            car_info["lapTime"] = format_time(elapsed - (lap_marks[-1] if lap_marks else 0.0))
            if lap_times:
                car_info["lastLapTime"] = format_time(lap_times[-1])
                car_info["fastestLapTime"] = format_time(min(lap_times))

        timing["cars"][car_id] = car_info

    return timing


def publish_timing(state):
    redis_client.publish('sse', json.dumps({
        "type": "timing",
        "data": build_timing(state)
    }))


## Database lap association ##
def sync_db_laps(car_id, car_state, end_ts=None):
    # Rewrite the laps column for this race from the lap boundaries, so lap+ and
    # lap- (corrections) both leave the database consistent. Points in the
    # current lap stay NULL until the next lap change or the end of the race
    if not os.path.exists(DB_PATH):
        return

    bounds = [car_state["start_ts"]] + [lap["car_ts"] for lap in car_state["laps"]]
    con = sqlite3.connect(DB_PATH, timeout=5)
    try:
        with con:
            for lap, (start, end) in enumerate(zip(bounds, bounds[1:])):
                con.execute(f"UPDATE {car_id} SET laps = ? WHERE timestamp >= ? AND timestamp < ?",
                            [lap, start, end])

            if end_ts is None:
                con.execute(f"UPDATE {car_id} SET laps = NULL WHERE timestamp >= ?", [bounds[-1]])
            else:
                con.execute(f"UPDATE {car_id} SET laps = ? WHERE timestamp >= ? AND timestamp <= ?",
                            [len(bounds) - 1, bounds[-1], end_ts])
    except sqlite3.Error as e:
        print(f"Error updating laps in {car_id}:", e)
    finally:
        con.close()


## Race control ##
def change_state(action):
    # Apply a change to the race state. Returns (state, error message or None)
    # action is "start", "stop", "pause", "resume", or "lap:<car_id>:<plus|minus>"
    with redis_client.lock(STATE_LOCK, timeout=10, blocking_timeout=10):
        state = load_state()
        status = race_status(state)
        now = time.time()

        if action == "start":
            if status in ("Running", "Paused"):
                return state, "Race already started"
            state = {
                "started_at": now,
                "ended_at": None,
                "paused_at": None,
                "paused_total": 0.0,
                "cars": {car_id: {"start_ts": car_timestamp(car_id), "laps": []} for car_id in CARS},
            }

        elif action == "stop":
            if status not in ("Running", "Paused"):
                return state, "Race not started"
            if state["paused_at"] is not None:
                state["paused_total"] += now - state["paused_at"]
                state["paused_at"] = None
            state["ended_at"] = now
            for car_id in CARS:
                sync_db_laps(car_id, state["cars"][car_id], end_ts=car_timestamp(car_id))

        elif action == "pause":
            if status != "Running":
                return state, "Race not running"
            state["paused_at"] = now

        elif action == "resume":
            if status != "Paused":
                return state, "Race not paused"
            state["paused_total"] += now - state["paused_at"]
            state["paused_at"] = None

        elif action.startswith("lap"):
            _, car_id, delta = action.split(":")
            if status not in ("Running", "Paused"):
                return state, "Race not started"
            car_state = state["cars"][car_id]

            if delta == "plus":
                # Never put a lap boundary before the previous one, which could
                # happen if the car's clock jumps or we fall back to server time
                prev_ts = car_state["laps"][-1]["car_ts"] if car_state["laps"] else car_state["start_ts"]
                car_state["laps"].append({
                    "race_time": race_elapsed(state, now),
                    "car_ts": max(car_timestamp(car_id), prev_ts),
                })
            elif car_state["laps"]:
                car_state["laps"].pop()
            else:
                return state, "No laps to remove"

            sync_db_laps(car_id, car_state)

        save_state(state)

    publish_timing(state)
    return state, None


def respond(action):
    state, error = change_state(action)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(build_timing(state))


## Authentication ##
def is_authed():
    return bool(redis_client.sismember(AUTHED_USERS_KEY, request.remote_addr))


@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        if request.get_data(as_text=True) != AUTH_CODE:
            return jsonify({"error": "Incorrect access code", "authed": False}), 401
        redis_client.sadd(AUTHED_USERS_KEY, request.remote_addr)
    return jsonify({"authed": is_authed()})


@app.route("/race/<action>", methods=["POST"])
def race_control(action):
    if not is_authed():
        return jsonify({"error": "Not authenticated"}), 401
    if action not in ("start", "stop", "pause", "resume"):
        return jsonify({"error": "Invalid race action"}), 404
    return respond(action)


@app.route("/laps/<car_id>/<delta>", methods=["POST"])
def lap_control(car_id, delta):
    if not is_authed():
        return jsonify({"error": "Not authenticated"}), 401
    if car_id not in CARS or delta not in ("plus", "minus"):
        return jsonify({"error": "Invalid lap action"}), 404
    return respond(f"lap:{car_id}:{delta}")


## Periodic timing broadcast ##
def is_leader():
    # Claim leadership if nobody holds it, or renew it if we already do. The key
    # expires after 2 seconds, so another worker takes over if the leader dies
    if redis_client.set(LEADER_KEY, WORKER_ID, nx=True, ex=2):
        return True
    if redis_client.get(LEADER_KEY) == WORKER_ID:
        redis_client.expire(LEADER_KEY, 2)
        return True
    return False


def record_telemetry(message):
    try:
        event = json.loads(message["data"])
        if event.get("type") != "telemetry":
            return
        data = event["data"]
        latest_telemetry[data["id"]] = {
            "timestamp": data.get("timestamp"),
            "received": time.time(),
        }
    except (ValueError, KeyError, TypeError):
        pass


def timing_loop():
    pubsub = None
    while True:
        try:
            if pubsub is None:
                pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe('sse')

            # Track telemetry from station.py until it's time for the next broadcast
            next_tick = time.time() + TIMING_INTERVAL
            while (remaining := next_tick - time.time()) > 0:
                message = pubsub.get_message(timeout=remaining)
                if message:
                    record_telemetry(message)

            if is_leader():
                publish_timing(load_state())

        except Exception as e:
            print("Timing loop error:", e)
            try:
                if pubsub is not None:
                    pubsub.close()
            except Exception:
                pass
            pubsub = None
            time.sleep(1)


threading.Thread(target=timing_loop, daemon=True).start()


# Main Dashboard page
@app.route("/")
def dashboard():
    return render_template('dashboard.html')

# Run the app for local testing
if __name__ == '__main__':
    app.run(threaded=True, debug=True, port=5000)
