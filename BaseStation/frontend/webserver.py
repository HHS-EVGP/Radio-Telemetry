from flask import Flask, render_template, jsonify, request
import waitress
import sqlite3
from datetime import datetime
import time

import socket
import select
import pickle
import os

app = Flask(__name__)

## Global variables ##
DBPATH = "BaseStation/EVGPTelemetry.sqlite"
AUTHCODE = "hhsevgp" # Make this whatever you like
authedusrs = []

laptime = None
racing = False
racetime = None
racetime_minutes = None
paused = False

# Variables stored in raceinfo
laps = None
prev_laptimes = []
when_race_started = None
paused_time = 0

# Restore pickled race data if applicable
# laps, prev_laptimes, and when_race_started
if os.path.exists("raceInfo.pkl"):
    with open("raceInfo.pkl", "rb") as file:
        try:
            raceinfo = pickle.load(file)

            if raceinfo is not None:
                racing = True
                laps = raceinfo['laps']
                prev_laptimes = raceinfo['prev_laptimes']
                when_race_started = raceinfo['when_race_started']
                paused_time = raceinfo['paused_time']

        except Exception as e:
            print("Error unpickling race data:", e)
            racing = False
            laps = None
            prev_laptimes = []
            when_race_started = None
            paused_time = 0

# Set up a global connection to the socket
SOCKETPATH = "/tmp/telemSocket"
socketConn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
socketConn.connect(SOCKETPATH)
print('Connected to socket:', SOCKETPATH)

lastSocketDump = [None] * 15  # * Data columns

# Function to clean up data for display
def clean_view(var):
    if var != None and var != 'Error':
        var = format(var, ".3f")
    return var

# Page to serve a json with data
@app.route("/getdata")
def getdata():
    global lastSocketDump, laps, laptime, racing, when_race_started, racetime, racetime_minutes, prev_laptimes, timestamp, paused_time

    # See if new data is available
    readable, _, _ = select.select([socketConn], [], [], 0)
    if readable:
        # Read data from the socket
        socketDump = socketConn.recv(1024)  # 1024 byte buffer
        data = pickle.loads(socketDump)
        lastSocketDump = data
    else:
        data = lastSocketDump

    # Unpack the data
    timestamp, throttle, brake_pedal, motor_temp, batt_1, batt_2, batt_3, batt_4, \
        amp_hours, voltage, current, speed, miles, GPS_x, GPS_y = data

    # Calculate current race time
    if racing and timestamp is not None:
        racetime = timestamp - when_race_started - paused_time

        # Calculate racetime_minutes if needed
        if racetime >= 60:
            racetime_minutes = racetime // 60
            racetime = racetime - racetime_minutes * 60

            # Convert racetime minutes to M:
            racetime_minutes = str(format(racetime_minutes, ".0f"))+":"

        # Format racetime
        if racetime < 10 and racetime_minutes is not None:
            racetime = format(racetime, ".1f")
            racetime = "0"+str(racetime)
        else:
            racetime = format(racetime, ".1f")

    # Calculate current lap time
    if racing and timestamp is not None:
        laptime = timestamp - when_race_started - sum(prev_laptimes) - paused_time

    return jsonify(
        systime=datetime.now().strftime("%H:%M:%S"),
        timestamp=time.strftime("%H:%M:%S", time.localtime(float(clean_view(timestamp)))) if timestamp is not None else None,
        throttle=clean_view(throttle),
        brake_pedal=clean_view(brake_pedal),
        motor_temp=clean_view(motor_temp),
        batt_1=clean_view(batt_1),
        batt_2=clean_view(batt_2),
        batt_3=clean_view(batt_3),
        batt_4=clean_view(batt_4),
        amp_hours=clean_view(amp_hours),
        voltage=clean_view(voltage),
        current=clean_view(current),
        speed=clean_view(speed),
        miles=clean_view(miles),
        GPS_x=clean_view(GPS_x),
        GPS_y=clean_view(GPS_y),
        laps=laps,
        laptime=format(laptime, ".1f") if laptime is not None else None,
        lastlaptime=format(prev_laptimes[-1], ".1f") if prev_laptimes else None,
        fastestlaptime=format(min(prev_laptimes), ".1f") if prev_laptimes else None,
        racetime=racetime,
        racetime_minutes=racetime_minutes,
        racing=racing,
        paused=paused
    )


# Respond to an authentication attempt
@app.route("/usrauth", methods=['POST'])
def usrauth():
    global authedusrs, AUTHCODE
    authattempt = request.get_data(as_text=True)

    if authattempt == AUTHCODE:
        if request.remote_addr not in authedusrs:
            authedusrs.append(request.remote_addr)
        return ('', 200)
    else:
        return ('Invalid authentication code', 401)


# Respond to an updated variable
@app.route("/usrupdate", methods=['POST'])
def usrupdate():
    global authedusrs, laps, laptime, prev_laptimes, racing, when_race_started, racetime, racetime_minutes, paused, paused_time, when_paused

    # Check if the user is authenticated
    if request.remote_addr not in authedusrs:
        return 'User not authenticated', 401

    # Check for command
    command = request.get_data(as_text=True)
    if not command:
        return 'No variable update command', 400

    con = sqlite3.connect(DBPATH)
    cur = con.cursor()

    if command == 'lap+' and racing:
        # Store the previous lap number in the database
        cur.execute("UPDATE main SET laps = ? WHERE time > ? AND laps IS NULL"
        ,[laps, when_race_started])
        con.commit()

        # Increment the lap number
        laps += 1
        if laptime is not None:
            prev_laptimes.append(laptime)
        laptime = 0

        # Update file dump
        raceinfo = {
            'laps': laps,
            'prev_laptimes': prev_laptimes,
            'when_race_started': when_race_started,
            'paused_time': paused_time
            }

        with open("raceInfo.pkl", "wb") as file:
            pickle.dump(raceinfo, file)

        return ('', 200)

    elif command == 'lap-' and racing:

        if laps > 0:
            # Remove all instances of the lap count
            cur.execute("UPDATE main SET laps = NULL WHERE time > ? AND laps = ?"
                        ,(when_race_started, laps,))
            con.commit()

            laps -= 1

            # Remove the previous lap time from the list
            prev_laptimes.pop()

            # Update file dump
            raceinfo = {
                'laps': laps,
                'prev_laptimes': prev_laptimes,
                'when_race_started': when_race_started,
                'paused_time': paused_time
                }

            with open("raceInfo.pkl", "wb") as file:
                pickle.dump(raceinfo, file)

        return ('', 200)

    elif command == 'pauseunpause':

        if paused == False:
            paused = True
            racing = False

            when_paused = timestamp

        else:
            racing = True

            paused = False
            paused_time += timestamp - when_paused

            # Update file dump
            raceinfo = {
                'laps': laps,
                'prev_laptimes': prev_laptimes,
                'when_race_started': when_race_started,
                'paused_time': paused_time
                }

            with open("raceInfo.pkl", "wb") as file:
                pickle.dump(raceinfo, file)

        return ('', 200)

    elif command == 'togglerace':
        if racing:
            racing = False

            # Reset to default values
            laps = None
            laptime = None
            prev_laptimes = []
            racetime = None
            racetime_minutes = None
            when_race_started = None
            paused_time = 0
            paused = False

            # Write file dump as None
            with open("raceInfo.pkl", "wb") as file:
                pickle.dump(None, file)

            return ('', 200)

        else:
            # Tie when_race_started to the latest timestamp in the database
            cur.execute("SELECT MAX(time) FROM main")
            when_race_started = cur.fetchone()[0]

            # If noting in the database, use the socket value
            if when_race_started == None:
                when_race_started = timestamp

            # If nothing form the socket, retrun an error
            if when_race_started == None:
                return ("No data! Unable to start race", 422)

            # Update file dump
            raceinfo = {
                'laps': laps,
                'prev_laptimes': prev_laptimes,
                'when_race_started': when_race_started,
                'paused_time': paused_time
                }

            with open("raceInfo.pkl", "wb") as file:
                pickle.dump(raceinfo, file)

            racing = True
            laps = 0

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


if __name__ == '__main__':
    waitress.serve(app, host='0.0.0.0', port=80, threads=8)
