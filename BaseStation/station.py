import waitress
import sqlite3
import time
import threading
import serial
import serial.tools.list_ports
import random
import json

from frontend.webserver import app
import sharedVars

# Function to set up a db table
def setupTable(table, con, cur):

    # Create the table if needed
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
        time REAL PRIMARY KEY,
        amp_hours REAL,
        voltage REAL,
        current REAL,
        speed REAL,
        miles REAL,
        gps_fix INTEGER,
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
        roll REAL,
        pitch REAL,
        heading REAL,
        altitude REAL,
        laps NUMERIC
    )
    """)
    con.commit()

    # Find a list of days that are present in the table
    cur.execute(f"""
        SELECT DISTINCT
            DATE(time, 'unixepoch') AS day
            FROM {table}
            ORDER BY day;
    """)
    days = cur.fetchall()

    ## Create individual views for each day in the table
    for day in days:
        cur.execute(f"""
        CREATE VIEW IF NOT EXISTS '{table + "-" + day[0]}'
        AS SELECT * FROM {table}
        WHERE DATE(time, 'unixepoch') = '{day[0]}';
        """)
    con.commit()


# Fnction to insert data into a certian table
def insertData(table, data, con, cur):
    insert_data_sql = f"""
        INSERT INTO {table} (
            time,
            amp_hours, voltage, current, speed, miles,
            gps_fix, GPS_x, GPS_y,
            throttle, brake, motor_temp, batt_1, batt_2, batt_3, batt_4,
            ambient_temp, roll, pitch, heading, altitude, laps
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null)
        """
        # laps is set to null when the data is inserted, and will be set by user input later

    # Insert the data
    cur.execute(insert_data_sql, data)
    con.commit()


# Background function to read and store data from serial
def readAndStoreData():
    # These lines are for a random data feed during testing
    #while True:
    #    sharedVars.data = [time.time()] + [random.uniform(0, 100) for i in range(20)]
    #    time.sleep(0.25)

    # Link the database to the python cursor
    con = sqlite3.connect(sharedVars.DBPATH)
    cur = con.cursor()

    # Set up the two tables
    setupTable("blue_445", con, cur)
    setupTable("red_111", con, cur)

    # Establish a serial connection to the esp32
    ser = None
    while ser is None:
        try:
            # Get a list of available devices
            ports = serial.tools.list_ports.comports()

            # Look for the USB to UART Bridge that is on the esp32
            for port in ports:
                if "CP210" in port.description or "CH340" in port.description:
                    serDevice = port.device
                    ser = serial.Serial(serDevice, 115200, timeout=1)

            time.sleep(1)
        except Exception as e:
            print("Error establishing serial connection:", e)
            time.sleep(1)


    # Constantly read and process the serial connection
    serErros = 0
    while True:
        try:
            # Read a line from the serial
            raw_line = ser.readline()

            # If we timed out, try again
            if not raw_line:
                continue

            # Clean up the line
            line = raw_line.decode(errors='ignore').strip()

            # Ignore empty lines after cleaning
            if not line:
                continue

            print("\n", line, "\n")

            if line.startswith("{"):
                # Parse JSON
                parsed_data = json.loads(line)

                data = [
                    parsed_data["timestamp"] / 100 if parsed_data["timestamp"] is not None else None,
                    parsed_data["ampHrs"],
                    parsed_data["voltage"],
                    parsed_data["current"],
                    parsed_data["speed"],
                    parsed_data["miles"],
                    parsed_data["fix"],
                    parsed_data["gpsX"],
                    parsed_data["gpsY"],
                    parsed_data["throttle"],
                    parsed_data["brake"],
                    parsed_data["motorTemp"],
                    parsed_data["batt1"],
                    parsed_data["batt2"],
                    parsed_data["batt3"],
                    parsed_data["batt4"],
                    parsed_data["ambientTemp"],
                    parsed_data["roll"],
                    parsed_data["pitch"],
                    parsed_data["heading"],
                    parsed_data["altitude"]
                ]

                id = parsed_data["id"]

                if id == "blue_445":
                    sharedVars.data_blue_445 = data
                elif id == "red_111":
                    sharedVars.data_red_111 = data
                else:
                    raise ValueError(f"Invalid car id: {id}")

                if data[0] is None:
                    print("No timestamp for packet!")
                    continue

                insertData(id, data, con, cur)

            else:
                raise ValueError(f"Invalid data received: {line}")

        except Exception as e:
            print("Data store error:", e)

            serErros += 1
            if serErros >= 5:
                print("Restarting Serial Connection!")
                try:
                    ser.close()
                    time.sleep(0.1)
                    ser = serial.Serial(serDevice, 115200, timeout=1)
                except Exception as e:
                    print("Error reestablishing serial connection:", e)

                serErros = 0
            time.sleep(0.1)

# Start the background thread to get data from serial
thread = threading.Thread(target=readAndStoreData, daemon=True)
thread.start()

# Start the app for testing
#app.run(host='0.0.0.0', port=5000, debug=False)

# Start the production server with waitress
waitress.serve(app, host='0.0.0.0', port=5000, threads=8)
