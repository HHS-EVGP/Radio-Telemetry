from flask import Flask, render_template, jsonify, request
import waitress
import sqlite3
from datetime import datetime
import time

import serial
import threading
import pickle
import os

app = Flask(__name__)

## Global variables ##
DBPATH = "BaseStation/EVGPTelemetry.sqlite"
AUTHCODE = "hhsevgp" # Make this whatever you like
authedUsrs = []
data = [None] * 22 # Number of data points

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

# Background function to read and store data from serial
def storeData():
    global data, DBPATH
    header = "$DATA,"

    # Link the database to the python cursor
    con = sqlite3.connect(DBPATH)
    cur = con.cursor()

    # If main table does not exist as a table, create it
    cur.execute("""
        CREATE TABLE IF NOT EXISTS main (
        time REAL UNIQUE PRIMARY KEY,
        amp_hours REAL,
        voltage REAL,
        current REAL,
        speed REAL,
        miles REAL,
        gps_fix, TEXT,
        angle, REAL,
        GPS_x REAL,
        GPS_y REAL,
        throttle REAL,
        brake REAL,
        motor_temp REAL,
        batt_1 REAL,
        batt_2 REAL,
        batt_3 REAL,
        batt_4 REAL,
        ambient_temp, REAL,
        rool REAL,
        pitch, REAL,
        heading, REAL,
        altitude, REAL,
        laps NUMERIC
    )
    """)
    con.commit()

    # Find a list of days that are present in the database
    cur.execute('''
        SELECT DISTINCT
            DATE(time, 'unixepoch') AS day
            FROM main
            ORDER BY day;
    ''')
    days = cur.fetchall()

    ## Create individual views for each existing day if they do not exist
    for day in days:
        cur.execute(f"""
        CREATE VIEW IF NOT EXISTS '{day[0]}'
        AS SELECT * FROM main
        WHERE DATE(time, 'unixepoch') = '{day[0]}';
        """)
    con.commit()

    insert_data_sql = """
        INSERT INTO main (
            time, throttle, brake, Motor_temp, batt_1, batt_2, batt_3, batt_4,
            amp_hours, voltage, current, speed, miles, GPS_X, GPS_Y
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

    # Establish a serial connection
    ser = None
    while ser is None:
        try:
            # Try to auto-detect a USB serial device
            for port in [f"/dev/ttyUSB{i}" for i in range(10)] + [f"/dev/ttyACM{i}" for i in range(10)]:
                try:
                    ser = serial.Serial(port, 115200, timeout=1)
                    print(f"Connected to serial port on {port}")
                    break
                except (serial.SerialException, OSError):
                    continue

            if ser is None:
                print("No serial device found, retrying.")
                time.sleep(1)
        except Exception as e:
            print("Serial connection error:", e)
            time.sleep(1)

    # Constantly read and process the serial connection
    while True:
        try:
            if ser.in_waiting:
                serDump = ser.read(ser.in_waiting)

                # If we don't have a complete line, read some more
                if not serDump.endswith("\n"):
                    continue

                # Decode and split by lines
                lines = serDump.decode(errors='ignore').splitlines()
                for line in lines:
                    if line.startswith(header):
                        data = line[len(header):].split(",")

                        # Insert into database
                        cur.execute(insert_data_sql, data)

        except Exception as e:
            print("Serial read error:", e)
            time.sleep(1)


# Function to clean up data for display
def cleanView(var, lenth):
    if var != None and var != 'Error':
        var = format(var, f".{lenth}f")
    return var

# Page to serve a json with data
@app.route("/getdata")
def getData():
    global data, laps, lapTime, racing, whenRaceStarted, raceTime, raceTimeMinutes, prevLapTimes, timestamp, pausedTime, endAmpHrs, paused

    # Unpack the data
    timestamp, ampHrs, voltage, current, speed, miles, fix, angle, gpsX, gpsY, \
        throttle, brakePedal, motorTemp, batt1, batt2, batt3, batt4, ambientTemp, \
        rool, pitch, heading, altitude = data

    # Calculate current race time
    if racing and timestamp is not None:
        raceTime = timestamp - whenRaceStarted - pausedTime

        # Calculate racetime_minutes if needed
        if raceTime >= 60:
            raceTimeMinutes = raceTime // 60
            raceTime = raceTime - raceTimeMinutes * 60

            # Convert racetime minutes to M:
            raceTimeMinutes = str(format(raceTimeMinutes, ".0f"))+":"

        # Format racetime
        if raceTime < 10 and raceTimeMinutes is not None:
            raceTime = format(raceTime, ".1f")
            raceTime = "0"+str(raceTime)
        else:
            raceTime = format(raceTime, ".1f")

    # Calculate current lap time
    if racing and timestamp is not None:
        lapTime = timestamp - whenRaceStarted - sum(prevLapTimes) - pausedTime

    # Estimate total amp hours that will be used in the race
    if racing and ampHrs is not None and timestamp is not None \
    or paused and ampHrs is not None and timestamp is not None:
        rawRaceTime = timestamp - whenRaceStarted - pausedTime

        # Formula derived from amp_hours/rawRacetime = endAmphrs/3600
        # Assuming a 60 minute race
        if rawRaceTime != 0:
            endAmpHrs = ampHrs * (3600 / rawRaceTime)

    return jsonify(
        systime=datetime.now().strftime("%H:%M:%S"),
        timestamp=time.strftime("%H:%M:%S", time.localtime(timestamp)) if timestamp is not None else None,
        throttle=cleanView(throttle, 3),
        brakePedal=cleanView(brakePedal, 3),
        motorTemp=cleanView(motorTemp, 3),
        batt1=cleanView(batt1, 3),
        batt2=cleanView(batt2, 3),
        batt3=cleanView(batt3, 3),
        batt4=cleanView(batt4, 3),
        ampHrs=cleanView(ampHrs, 3),
        endAmpHrs=cleanView(endAmpHrs, 3),
        voltage=cleanView(voltage, 3),
        current=cleanView(current, 3),
        speed=cleanView(speed, 3),
        miles=cleanView(miles, 3),
        gpsX=cleanView(gpsX, 3),
        gpsY=cleanView(gpsY, 3),
        laps=laps,
        lapTime=cleanView(lapTime, 1),
        lastLapTime=cleanView(float(prevLapTimes[-1]), 1) if len(prevLapTimes) != 0 else None,
        fastestLapTime=cleanView(float(min(prevLapTimes)), 1) if len(prevLapTimes) != 0 else None,
        raceTime=raceTime,
        raceTimeMinutes=raceTimeMinutes,
        racing=racing,
        paused=paused,
        authed=True if request.remote_addr in authedUsrs else False
    )


# Respond to an authentication attempt
@app.route("/usrauth", methods=['POST'])
def usrAuth():
    global authedUsrs, AUTHCODE
    authAttempt = request.get_data(as_text=True)

    if authAttempt == AUTHCODE:
        if request.remote_addr not in authedUsrs:
            authedUsrs.append(request.remote_addr)
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

    con = sqlite3.connect(DBPATH)
    cur = con.cursor()

    if command == 'lap+' and racing:
        # Store the previous lap number in the database
        cur.execute("UPDATE main SET laps = ? WHERE time > ? AND laps IS NULL"
        ,[laps, whenRaceStarted])
        con.commit()

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

        return ('Play Sound', 200)

    elif command == 'lap-' and racing:

        if laps > 0:
            # Remove all instances of the lap count
            cur.execute("UPDATE main SET laps = NULL WHERE time > ? AND laps = ?"
                        ,(whenRaceStarted, laps,))
            con.commit()

            laps -= 1

            # Remove the previous lap time from the list
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

            return ('', 200)

        else:

            # Tie whenRaceStarted to the current timestamp
            whenRaceStarted = timestamp

            #cur.execute("SELECT MAX(time) FROM main")
            #whenRaceStarted = cur.fetchone()[0]

            # If we don't have a current value, return an error
            if whenRaceStarted == None:
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
    # Start the background thread to get data from serial
    thread = threading.Thread(target=storeData, daemon=True)
    thread.start()

    # Start the server
    waitress.serve(app, host='0.0.0.0', port=80, threads=8)
