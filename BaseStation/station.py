import os
import sqlite3
import time
import json
import random

import redis
import serial
import serial.tools.list_ports

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "EVGPTelemetry.sqlite")

# Toggle the random data feed during testing
RANDOM_DATA = True

# Car ids, these are also the database table names (keep in sync with webserver.py)
CARS = ["blue_445", "red_111"]

# Telemetry fields stored in the database, in column order (after timestamp)
# The names match the packet fields in the car firmware and the JSON from the receiver
DATA_FIELDS = [
    "ampHrs", "voltage", "current", "speed", "distance",
    "fix", "gpsX", "gpsY",
    "throttle", "brake", "motorTemp", "batt1", "batt2", "batt3", "batt4",
    "ambientTemp", "roll", "pitch", "heading", "altitude",
]

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)


def setup_table(table, con):
    # Create the table if needed
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            timestamp REAL PRIMARY KEY,
            ampHrs REAL,
            voltage REAL,
            current REAL,
            speed REAL,
            distance REAL,
            fix INTEGER,
            gpsX REAL,
            gpsY REAL,
            throttle REAL,
            brake REAL,
            motorTemp REAL,
            batt1 REAL,
            batt2 REAL,
            batt3 REAL,
            batt4 REAL,
            ambientTemp REAL,
            roll REAL,
            pitch REAL,
            heading REAL,
            altitude REAL,
            laps NUMERIC
        )
    """)

    # Create a view (named like "blue_445-2026-11-08") for each day that has data
    # Days are only checked at startup, so today's view appears after a restart
    days = con.execute(f"""
        SELECT DISTINCT DATE(timestamp, 'unixepoch') AS day
        FROM {table}
        ORDER BY day
    """).fetchall()

    for (day,) in days:
        con.execute(f"""
            CREATE VIEW IF NOT EXISTS "{table}-{day}"
            AS SELECT * FROM {table}
            WHERE DATE(timestamp, 'unixepoch') = '{day}'
        """)
    con.commit()


def publish_telemetry(data):
    # flask-sse is listening on the channel "sse", "type" is the SSE event name
    redis_client.publish('sse', json.dumps({
        "type": "telemetry",
        "data": data
    }))


def insert_data(table, data, con):
    columns = ["timestamp"] + DATA_FIELDS
    values = [data.get(column) for column in columns]

    # laps is left null here; webserver.py fills it in from the lap timing
    con.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        values,
    )
    con.commit()


def random_data(car_id):
    data = {field: random.uniform(0, 100) for field in DATA_FIELDS}
    data["id"] = car_id
    data["timestamp"] = time.time()
    data["fix"] = random.choice([True, False])
    return data


def run_random_feed():
    while True:
        for car_id in CARS:
            publish_telemetry(random_data(car_id))
            time.sleep(1)

        print("fake data sent")


def connect_serial():
    # Keep trying until we find the receiver esp32 (by its USB to UART bridge chip)
    while True:
        try:
            for port in serial.tools.list_ports.comports():
                if "CP210" in port.description or "CH340" in port.description:
                    print("Connecting to", port.device)
                    return serial.Serial(port.device, 115200, timeout=1)
        except Exception as e:
            print("Error establishing serial connection:", e)

        time.sleep(1)


def handle_line(line, con):
    data = json.loads(line)

    car_id = data.get("id")
    if car_id not in CARS:
        raise ValueError(f"Unknown car id: {car_id}")

    # The receiver sends the timestamp in milliseconds, convert it back to seconds
    if data["timestamp"] is not None:
        data["timestamp"] /= 1000

    # Send the data to the dashboard
    publish_telemetry(data)

    if data["timestamp"] is None:
        print("No timestamp for packet! Skipping database insertion!")
        return

    insert_data(car_id, data, con)


def main():
    if RANDOM_DATA:
        run_random_feed()

    con = sqlite3.connect(DB_PATH)
    for car_id in CARS:
        setup_table(car_id, con)

    ser = connect_serial()

    # Constantly read and process the serial connection
    serial_errors = 0
    while True:
        try:
            line = ser.readline().decode(errors='ignore').strip()
            serial_errors = 0
        except Exception as e:
            print("Serial read error:", e)

            # Reconnect after several errors in a row (e.g. the receiver was unplugged)
            serial_errors += 1
            if serial_errors >= 5:
                print("Restarting Serial Connection!")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = connect_serial()
                serial_errors = 0

            time.sleep(0.1)
            continue

        # Empty if the read timed out
        if not line:
            continue

        print(line)

        # Skip non JSON lines, like error messages from the receiver
        if not line.startswith("{"):
            continue

        try:
            handle_line(line, con)
        except (ValueError, KeyError, TypeError, sqlite3.Error) as e:
            print("Data store error:", e)


if __name__ == "__main__":
    main()
