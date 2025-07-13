# This non critical file generates fake data to feed the webpage
# for use in testing when no radio is avalable

import socket
import pickle
import os
import random
import time
import sqlite3

# Link the database to the python cursor
con = sqlite3.connect("../EVGPTelemetry.sqlite")
cur = con.cursor()

# If main table does not exist as a table, create it
create_table_sql = """
    CREATE TABLE IF NOT EXISTS main (
    time REAL UNIQUE PRIMARY KEY,
    amp_hours REAL,
    voltage REAL,
    current REAL,
    speed REAL,
    miles REAL,
    throttle REAL,
    brake REAL,
    motor_temp REAL,
    batt_1 REAL,
    batt_2 REAL,
    batt_3 REAL,
    batt_4 REAL,
    GPS_x REAL,
    GPS_y REAL,
    laps NUMERIC
)
"""
cur.execute(create_table_sql)
con.commit()
con.close()

SOCKETPATH = "/tmp/telemSocket"

# Remove existing socket file if it exists
if os.path.exists(SOCKETPATH):
    os.remove(SOCKETPATH)

# Create a Unix socket and listen
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(SOCKETPATH)
server.listen(1)

print("Server is waiting for connection...")
sock, _ = server.accept()
print("Client connected.")

while True:
    #input("Press Enter to send next data row")

    # Randomize socket data
    values = [time.time()] + [random.uniform(0.0, 1000.0) for i in range(14)]

    # send data
    data = pickle.dumps(values)
    sock.sendall(data)

    time.sleep(0.25)
