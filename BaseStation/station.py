import waitress
import sqlite3
import time
import threading
import serial
import serial.tools.list_ports
import random
import json
import math

from frontend.webserver import app
import sharedVars


# Background function to read and store data from serial
def storeData():
    # Theese lines are for a random data feed during testing
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
            time,
            amp_hours, voltage, current, speed, miles,
            gps_fix, GPS_x, GPS_y,
            throttle, brake, motor_temp, batt_1, batt_2, batt_3, batt_4,
            ambient_temp, rool, pitch, heading, altitude, laps
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null)
        """
    # laps is set to null when the data is inserted, and will be set by user input later

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

        except Exception as e:
            print("Error establishing serial connection:", e)
            time.sleep(1)

    # Constantly read and process the serial connection
    serDump = b''
    serErros = 0
    while True:
        try:
            if ser.in_waiting:
                # Read a character
                c = ser.read(1)
                serDump += c

                # If we don't have a newline, read some more
                if c != b'\n':
                    continue

                # Decode and split by lines
                lines = serDump.decode(errors='ignore').splitlines()
                for line in lines:

                    print("\n", line, "\n")

                    if line.startswith("{"):
                        # Parse the JSON data
                        jsonStr = line
                        parsed_data = json.loads(jsonStr)

                        # Convert the json into a list
                        data = [
                            parsed_data["timestamp"],
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

                        # Share the data with the webpage
                        sharedVars.data = data

                        # Reset the serial dump
                        serDump = b'';

                        # Exclude the data from the database if there is no timestamp
                        if math.isnan(data[0]):
                            print("No timestamp for packet!")
                            continue

                        # Insert into database
                        cur.execute(insert_data_sql, data)

                    # If we got trash data, throw an error
                    else:
                        raise ValueError(f"Invalid data received: {line}")


        except Exception as e:
            print("Data store error:", e)

            # Restart the serial connection after 5 errors
            serErros += 1
            if serErros >= 5:
                print("Restarting Serial Connection!")

                # Disconnect and reconnect the serial
                try:
                    serDump = b'';
                    ser.close()

                    time.sleep(0.1)
                    ser = serial.Serial(serDevice, 115200, timeout=1)
                except Exception as e:
                    print("Error reestablishing serial connection:", e)

                serErros = 0
            time.sleep(0.1)


# Start the background thread to get data from serial
thread = threading.Thread(target=storeData, daemon=True)
thread.start()

# Start the webserver
app.run(host='0.0.0.0', port=5000, debug=False)

#waitress.serve(app, host='0.0.0.0', port=80, threads=8)
