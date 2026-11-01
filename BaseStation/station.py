import sqlite3
import time
import json
import redis

import serial
import serial.tools.list_ports
import random

DBPATH = "BaseStation/EVGPTelemetry.sqlite"

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

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

# Function to make a random telemetry packet
def random_data(id):
    data = {
        "id": id,
        "timestamp": time.time(),
        "ampHrs": random.uniform(0, 100),
        "voltage": random.uniform(0, 100),
        "current": random.uniform(0, 100),
        "speed": random.uniform(0, 100),
        "miles": random.uniform(0, 100),
        "fix": random.uniform(0, 100),
        "gpsX": random.uniform(0, 100),
        "gpsY": random.uniform(0, 100),
        "throttle": random.uniform(0, 100),
        "brake": random.uniform(0, 100),
        "motorTemp": random.uniform(0, 100),
        "batt1": random.uniform(0, 100),
        "batt2": random.uniform(0, 100),
        "batt3": random.uniform(0, 100),
        "batt4": random.uniform(0, 100),
        "ambientTemp": random.uniform(0, 100),
        "roll": random.uniform(0, 100),
        "pitch": random.uniform(0, 100),
        "heading": random.uniform(0, 100),
        "altitude": random.uniform(0, 100),
    }
    return json.dumps(data)

# These lines are for a random data feed during testing
#while True:
#    redis_client.publish('sse', json.dumps({
#        "type": "telemetry",
#        "data": json.loads(random_data("blue_445"))  # Pass dict instead of string
#    }))
#    time.sleep(1)
#
#    redis_client.publish('sse', json.dumps({
#        "type": "telemetry",
#        "data": json.loads(random_data("red_111"))  # Pass dict instead of string
#    }))
#    time.sleep(1)
#
#    print("fake data sent")

# Link the database to the python cursor
con = sqlite3.connect(DBPATH)
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
            data = json.loads(line)

            # Convert the timestamp back from miliseconds to seconds
            if data["timestamp"] != None:
                data["timestamp"] /= 100

            # Trigger a SSE broadcast to clients using redis
            # flask-sse is listening on the channel "sse"
            redis_client.publish('sse', json.dumps({
                "type": "telemetry",  # Event type expected by flask-sse
                "data": data
            }))

            if data["timestamp"] is None:
                print("No timestamp for packet! Skipping database insertion!")
                continue

            # Turn the data into a list for insertion into the database
            id = data["id"]
            dataList = [
                data["timestamp"],
                data["ampHrs"],
                data["voltage"],
                data["current"],
                data["speed"],
                data["miles"],
                data["fix"],
                data["gpsX"],
                data["gpsY"],
                data["throttle"],
                data["brake"],
                data["motorTemp"],
                data["batt1"],
                data["batt2"],
                data["batt3"],
                data["batt4"],
                data["ambientTemp"],
                data["roll"],
                data["pitch"],
                data["heading"],
                data["altitude"]
            ]

            # Insert the data into the database
            insertData(id, dataList, con, cur)

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
