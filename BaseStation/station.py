import waitress
import sqlite3
import time
import threading
import serial
import random

from frontend.webserver import app
import sharedVars


# Background function to read and store data from serial
def storeData():
    serialHeader = "$DATA,"

    # Theese lines are for a random data feed for testing
    #while True:
    #    sharedVars.data = [time.time()] + [random.uniform(0, 100) for i in range(20)]
    #    time.sleep(0.25)

    # Link the database to the python cursor
    con = sqlite3.connect(sharedVars.DBPATH)
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
        gps_fix TEXT,
        GPS_x REAL,
        GPS_y REAL,
        throttle REAL,
        brake REAL,
        motor_temp REAL,
        batt_1 REAL,
        batt_2 REAL,
        batt_3 REAL,
        batt_4 REAL,
        ambient_temp REAL,
        rool REAL,
        pitch REAL,
        heading REAL,
        altitude REAL,
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
                    if line.startswith(serialHeader):
                        sharedVars.data = line[len(serialHeader):].split(",")

                        # Insert into database
                        cur.execute(insert_data_sql, sharedVars.data)

        except Exception as e:
            print("Serial read error:", e)
            time.sleep(1)


# Start the background thread to get data from serial
thread = threading.Thread(target=storeData, daemon=True)
thread.start()

# Start the webserver
app.run(host='0.0.0.0', port=5000, debug=False)

#waitress.serve(app, host='0.0.0.0', port=80, threads=8)
