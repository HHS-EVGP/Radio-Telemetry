import time
import math
import random

from station import CARS, publish_telemetry

# Sends fake but plausible telemetry for each car driving laps of an oval track
# Data is only published to the dashboard, nothing is saved to the database
RATE = 5  # Packets per second per car, like the real cars
LAP_LENGTH = 900  # Meters
TRACK_WIDTH, TRACK_HEIGHT = 200, 60  # Half the size of the oval, in meters
GPS_ORIGIN_X, GPS_ORIGIN_Y = -8574000, 4705000  # Where the track is on the map, in meters
METERS_PER_MILE = 1609.34


def new_car():
    return {"lap": random.random(), "distance": 0.0, "ampHrs": 0.0, "wattHrs": 0.0,
            "motorTemp": 25.0, "restVoltage": None, "resistance": None, "battTimer": 0.0}


def step(car_id, car, dt):
    # Angle around the oval, the corners are at the ends (0 and pi)
    angle = 2 * math.pi * car["lap"]
    corner = math.cos(angle) ** 2  # 1 in the middle of a corner, 0 on the straights

    # Slower in the corners, faster on the straights. This averages about 18 mph,
    # which uses about the 590 Wh budget in the hour long race
    speed = 22 - 8 * corner + random.uniform(-1, 1)  # mph
    meters = speed * METERS_PER_MILE / 3600 * dt
    car["lap"] = (car["lap"] + meters / LAP_LENGTH) % 1
    car["distance"] += meters / METERS_PER_MILE

    # The battery sags as it is used and collapses after about 12.5 Ah
    used = car["ampHrs"]
    resistance = 0.1 + max(0.0, used - 11) * 0.03
    rest_voltage = 51 - 0.25 * used - max(0.0, used - 12.5) * 4
    # Power from the clean lap fit used by the dashboard: Wh per mile = 1.87 * mph - 1.6
    power = (1.87 * speed - 1.6) * speed
    current = power / rest_voltage
    voltage = rest_voltage - resistance * current
    car["ampHrs"] += current * dt / 3600
    car["wattHrs"] += voltage * current * dt / 3600
    car["motorTemp"] += (current * 0.02 - (car["motorTemp"] - 25) * 0.002) * dt

    # Like the car, the battery estimate only updates every 30 seconds
    car["battTimer"] += dt
    if car["battTimer"] >= 30:
        car["battTimer"] = 0
        car["restVoltage"] = rest_voltage
        car["resistance"] = resistance

    return {
        "id": car_id,
        "timestamp": time.time(),
        "ampHrs": car["ampHrs"],
        "voltage": voltage,
        "current": current,
        "speed": speed,
        "distance": car["distance"],
        "wattHrs": car["wattHrs"],
        "restVoltage": car["restVoltage"],
        "resistance": car["resistance"],
        "fix": True,
        "gpsX": GPS_ORIGIN_X + TRACK_WIDTH * math.cos(angle),
        "gpsY": GPS_ORIGIN_Y + TRACK_HEIGHT * math.sin(angle),
        "throttle": min(1000.0, current * 25),
        "brake": 0.0,
        "motorTemp": car["motorTemp"],
        "batt1": 28 + used * 0.8,
        "batt2": 27 + used * 0.9,
        "batt3": 29 + used * 0.7,
        "batt4": 28 + used * 1.0,
        "ambientTemp": 22.0,
        "roll": 6 * corner,
        "pitch": 0.0,
        # Compass heading of the direction the car is moving (counterclockwise around the oval)
        "heading": math.degrees(math.atan2(-TRACK_WIDTH * math.sin(angle), TRACK_HEIGHT * math.cos(angle))) % 360,
        "altitude": 50.0,
    }


def main():
    cars = {car_id: new_car() for car_id in CARS}
    while True:
        for car_id, car in cars.items():
            publish_telemetry(step(car_id, car, 1 / RATE))
        time.sleep(1 / RATE)


if __name__ == "__main__":
    main()
