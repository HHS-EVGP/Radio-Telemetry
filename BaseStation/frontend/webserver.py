from flask import Flask, render_template, jsonify, request, Response
import sqlite3
from datetime import datetime
import time

import pickle
import os
import json
import queue
import threading

app = Flask(__name__)

## Global variables ##
import sharedVars

AUTHCODE = "hhsevgp" # Make this whatever you like
authedUsrs = []

endAmpHrs = None
lapTime = None
racing = False
raceTime = None
raceTimeMinutes = None
paused = False

# Variables stored in raceInfo
laps = None
prevLapTimes = []
whenRaceStarted = None
pausedTime = 0
whenPaused = None

# Restore pickled race data if applicable
if os.path.exists("raceInfo.pkl"):
    with open("raceInfo.pkl", "rb") as file:
        try:
            raceInfo = pickle.load(file)

            if raceInfo is not None:
                racing = True
                laps = raceInfo['laps']
                prevLapTimes = raceInfo['prev_laptimes']
                whenRaceStarted = raceInfo['when_race_started']
                pausedTime = raceInfo['paused_time']
                whenPaused = raceInfo['when_paused']

                if whenPaused is not None:
                    paused = True
                    racing = False

        except Exception as e:
            print("Error unpickling race data:", e)
            racing = False
            laps = None
            prevLapTimes = []
            whenRaceStarted = None
            pausedTime = 0
            whenPaused = None


# Function to clean up data for display
def cleanView(var, lenth):
    if var is not None and var != 'Error':
        var = format(var, f".{lenth}f")
    return var

# Attach cleanView to the Flask app
app.cleanView = cleanView


# SSE client subscribers
_client_listeners = set()
_client_lock = threading.Lock()


def add_client_listener(client_queue, remote_addr):
    with _client_lock:
        _client_listeners.add((client_queue, remote_addr))


def remove_client_listener(client_queue):
    with _client_lock:
        to_remove = [item for item in _client_listeners if item[0] is client_queue]
        for item in to_remove:
            _client_listeners.remove(item)


def broadcast_to_clients(payload_maker):
    with _client_lock:
        subscribers = list(_client_listeners)
    for client_queue, remote_addr in subscribers:
        try:
            is_authed = remote_addr in authedUsrs
            payload = payload_maker(is_authed)
            client_queue.put_nowait(payload)
        except queue.Full:
            pass
        except Exception as e:
            print("Error dispatching SSE to client queue:", e)


def format_telemetry(raw_data, car_id=None, authed=False):
    global laps, lapTime, racing, whenRaceStarted, raceTime, raceTimeMinutes, prevLapTimes, pausedTime, endAmpHrs, paused

    if not raw_data or len(raw_data) < 21:
        raw_data = [None] * 21

    timestamp, ampHrs, voltage, current, speed, miles, gpsFix, gpsX, gpsY, \
        throttle, brakePedal, motorTemp, batt1, batt2, batt3, batt4, ambientTemp, \
        roll, pitch, heading, altitude = raw_data[:21]

    # Calculate current race time
    if racing and timestamp is not None and whenRaceStarted is not None:
        calcRaceTime = timestamp - whenRaceStarted - pausedTime

        # Calculate racetime_minutes if needed
        if calcRaceTime >= 60:
            raceTimeMinutes = calcRaceTime // 60
            calcRaceTime = calcRaceTime - raceTimeMinutes * 60

            # Convert racetime minutes to M:
            raceTimeMinutes = str(format(raceTimeMinutes, ".0f")) + ":"
        else:
            raceTimeMinutes = ""

        # Format racetime
        if calcRaceTime < 10 and raceTimeMinutes != "":
            raceTime = "0" + str(format(calcRaceTime, ".1f"))
        else:
            raceTime = format(calcRaceTime, ".1f")

    # Calculate current lap time
    if racing and timestamp is not None and whenRaceStarted is not None:
        lapTime = timestamp - whenRaceStarted - sum(prevLapTimes) - pausedTime

    # Estimate total amp hours that will be used in the race
    if ((racing or paused) and ampHrs is not None and timestamp is not None and whenRaceStarted is not None):
        rawRaceTime = timestamp - whenRaceStarted - pausedTime

        # Formula derived from amp_hours/rawRacetime = endAmphrs/3600
        # Assuming a 60 minute race
        if rawRaceTime != 0:
            endAmpHrs = ampHrs * (3600 / rawRaceTime)

    formatted_timestamp = None
    if timestamp is not None:
        try:
            formatted_timestamp = time.strftime("%H:%M:%S", time.localtime(timestamp))
        except Exception:
            formatted_timestamp = str(timestamp)

    last_lap_time = None
    if len(prevLapTimes) != 0:
        try:
            last_lap_time = cleanView(float(prevLapTimes[-1]), 1)
        except (ValueError, TypeError):
            last_lap_time = None

    fastest_lap_time = None
    if len(prevLapTimes) != 0:
        try:
            fastest_lap_time = cleanView(float(min(prevLapTimes)), 1)
        except (ValueError, TypeError):
            fastest_lap_time = None

    return {
        # Statuses
        "systime": datetime.now().strftime("%H:%M:%S"),
        "timestamp": formatted_timestamp,
        "carId": car_id,
        "throttle": cleanView(throttle, 3),
        "brakePedal": cleanView(brakePedal, 3),

        # Temps
        "motorTemp": cleanView(motorTemp, 3),
        "batt1": cleanView(batt1, 3),
        "batt2": cleanView(batt2, 3),
        "batt3": cleanView(batt3, 3),
        "batt4": cleanView(batt4, 3),
        "ambientTemp": cleanView(ambientTemp, 3),

        # CA
        "ampHrs": cleanView(ampHrs, 3),
        "endAmpHrs": cleanView(endAmpHrs, 3),
        "voltage": cleanView(voltage, 3),
        "current": cleanView(current, 3),
        "speed": cleanView(speed, 3),
        "miles": cleanView(miles, 3),

        # Position
        "gpsFix": bool(gpsFix) if gpsFix is not None else None,
        "gpsX": cleanView(gpsX, 3),
        "gpsY": cleanView(gpsY, 3),
        "roll": cleanView(roll, 3),
        "pitch": cleanView(pitch, 3),
        "heading": cleanView(heading, 3),
        "altitude": cleanView(altitude, 3),

        # Race info
        "laps": laps,
        "lapTime": cleanView(lapTime, 1),
        "lastLapTime": last_lap_time,
        "fastestLapTime": fastest_lap_time,
        "raceTime": raceTime,
        "raceTimeMinutes": raceTimeMinutes,
        "racing": racing,
        "paused": paused,
        "authed": authed
    }


def broadcast_current_state():
    current_data = getattr(sharedVars, "data", [None] * 21)
    car_id = getattr(sharedVars, "latest_car_id", "blue_445")
    broadcast_to_clients(lambda authed: format_telemetry(current_data, car_id=car_id, authed=authed))


def on_telemetry_stream(car_id, data_point):
    broadcast_to_clients(lambda authed: format_telemetry(data_point, car_id=car_id, authed=authed))


# Subscribe to data points stream from station.py via sharedVars
sharedVars.add_listener(on_telemetry_stream)


# Server-Sent Events endpoint to stream data points to clients
@app.route("/stream")
@app.route("/events")
def sse_stream():
    client_queue = queue.Queue(maxsize=100)
    remote_addr = request.remote_addr
    is_authed = remote_addr in authedUsrs

    # Immediately queue current state for newly connected client
    current_data = getattr(sharedVars, "data", [None] * 21)
    car_id = getattr(sharedVars, "latest_car_id", "blue_445")
    try:
        initial_payload = format_telemetry(current_data, car_id=car_id, authed=is_authed)
        client_queue.put_nowait(initial_payload)
    except Exception as e:
        print("Error enqueueing initial state:", e)

    add_client_listener(client_queue, remote_addr)

    def event_stream():
        try:
            while True:
                try:
                    payload = client_queue.get(timeout=15)
                    yield f"data: {json.dumps(payload)}\n\n"
                except queue.Empty:
                    # Keepalive comment to prevent timeouts
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            remove_client_listener(client_queue)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# Page to serve a json with data (kept for backwards compatibility)
@app.route("/getdata")
def getData():
    current_data = getattr(sharedVars, "data", [None] * 21)
    car_id = getattr(sharedVars, "latest_car_id", "blue_445")
    is_authed = request.remote_addr in authedUsrs
    return jsonify(format_telemetry(current_data, car_id=car_id, authed=is_authed))


# Respond to an authentication attempt
@app.route("/usrauth", methods=['POST'])
def usrAuth():
    global authedUsrs, AUTHCODE
    authAttempt = request.get_data(as_text=True)

    if authAttempt == AUTHCODE:
        if request.remote_addr not in authedUsrs:
            authedUsrs.append(request.remote_addr)
        broadcast_current_state()
        return ('', 200)
    else:
        return ('Invalid authentication code', 401)


# Respond to an updated variable
@app.route("/usrupdate", methods=['POST'])
def usrUpdate():
    global authedUsrs, laps, lapTime, prevLapTimes, racing, whenRaceStarted, raceTime, raceTimeMinutes, paused, pausedTime, whenPaused, endAmpHrs

    # Check if the user is authenticated
    if request.remote_addr not in authedUsrs:
        return 'User not authenticated', 401

    # Check for command
    command = request.get_data(as_text=True)
    if not command:
        return 'No variable update command', 400

    def update_db_laps(new_laps_val, condition_laps=None):
        db_paths = [
            sharedVars.DBPATH,
            os.path.join(os.path.dirname(__file__), "..", "EVGPTelemetry.sqlite"),
            "EVGPTelemetry.sqlite"
        ]
        con = None
        for p in db_paths:
            try:
                parent = os.path.dirname(p)
                if parent and not os.path.exists(parent):
                    continue
                con = sqlite3.connect(p)
                break
            except Exception:
                continue

        if con is None:
            return

        try:
            cur = con.cursor()
            for table in ["blue_445", "red_111", "main"]:
                try:
                    if condition_laps is None:
                        cur.execute(f"UPDATE {table} SET laps = ? WHERE time > ? AND laps IS NULL", [new_laps_val, whenRaceStarted])
                    else:
                        cur.execute(f"UPDATE {table} SET laps = ? WHERE time > ? AND laps = ?", [new_laps_val, whenRaceStarted, condition_laps])
                    con.commit()
                except sqlite3.OperationalError:
                    pass
        finally:
            con.close()

    latest_data = getattr(sharedVars, "data", [None] * 21)
    timestamp = latest_data[0] if latest_data else None

    if command == 'lap+' and racing:
        # Store the previous lap number in the database
        update_db_laps(laps)

        # Increment the lap number
        laps += 1
        if lapTime is not None:
            prevLapTimes.append(lapTime)
        lapTime = 0

        # Update file dump
        raceInfo = {
            'laps': laps,
            'prev_laptimes': prevLapTimes,
            'when_race_started': whenRaceStarted,
            'paused_time': pausedTime,
            'when_paused': whenPaused
        }

        with open("raceInfo.pkl", "wb") as file:
            pickle.dump(raceInfo, file)

        broadcast_current_state()
        return ('Play Sound', 200)

    elif command == 'lap-' and racing:
        if laps > 0:
            # Remove all instances of the lap count
            update_db_laps(None, condition_laps=laps)

            laps -= 1

            # Remove the previous lap time from the list
            if len(prevLapTimes) > 0:
                prevLapTimes.pop()

            # Update file dump
            raceInfo = {
                'laps': laps,
                'prev_laptimes': prevLapTimes,
                'when_race_started': whenRaceStarted,
                'paused_time': pausedTime,
                'when_paused': whenPaused
            }

            with open("raceInfo.pkl", "wb") as file:
                pickle.dump(raceInfo, file)

        broadcast_current_state()
        return ('', 200)

    elif command == 'pauseunpause':
        if not racing and not paused:
            return ("Not racing!", 400)

        if not paused:
            paused = True
            racing = False
            whenPaused = timestamp
        else:
            paused = False
            racing = True
            if timestamp is not None and whenPaused is not None:
                pausedTime += timestamp - whenPaused
            whenPaused = None

        # Update file dump
        raceInfo = {
            'laps': laps,
            'prev_laptimes': prevLapTimes,
            'when_race_started': whenRaceStarted,
            'paused_time': pausedTime,
            'when_paused': whenPaused
        }

        with open("raceInfo.pkl", "wb") as file:
            pickle.dump(raceInfo, file)

        broadcast_current_state()
        return ('', 200)

    elif command == 'togglerace':
        if racing or paused:
            racing = False

            # Reset to default values
            laps = None
            lapTime = None
            prevLapTimes = []
            raceTime = None
            raceTimeMinutes = None
            whenRaceStarted = None
            pausedTime = 0
            paused = False
            endAmpHrs = None

            # Write file dump as None
            with open("raceInfo.pkl", "wb") as file:
                pickle.dump(None, file)

            broadcast_current_state()
            return ('', 200)

        else:
            # Tie whenRaceStarted to the current timestamp
            whenRaceStarted = timestamp

            # If we don't have a current value, return an error
            if whenRaceStarted is None:
                return ("No data! Unable to start race", 422)

            # Initiate laps
            laps = 0

            # Update file dump
            raceInfo = {
                'laps': laps,
                'prev_laptimes': prevLapTimes,
                'when_race_started': whenRaceStarted,
                'paused_time': pausedTime,
                'when_paused': whenPaused
            }

            with open("raceInfo.pkl", "wb") as file:
                pickle.dump(raceInfo, file)

            racing = True
            broadcast_current_state()
            return ('', 200)

    else:
        return 'Invalid variable update command', 400

# Main Dashboard page
@app.route("/")
def dashboard():
    return render_template('dashboard.html')


# Page for analyzing the car's path
@app.route("/map")
def map():
    return render_template('map.html')


# Debug page
@app.route("/debug")
def debug():
    return render_template('debug.html')
