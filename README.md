# EVGP Data Collection and Visualization System

This project is a data collection and visualization system for an electric race car using two ESP32s and a computer. Data is collected, logged, transmitted over radio, and visualized in real time.

## Who Are We?

The Harrisonburg High School Electric Vehicle Grand Prix team is a student-run racing team that builds an electric car and races it in an endurance race. As of 2025, we are a four-year-old team, and from the start, live data has been an important part of our race strategy.

## Check out our data archive [here](https://github.com/HHS-EVGP/Data-Archive)!

## Building the System

### System Structure

An ESP32-powered data board on the car collects data from various points, logs the data on an SD card, and transmits it live using [ESP-NOW](https://www.espressif.com/en/solutions/low-power-solutions/esp-now).

#### Points of Data Collected
- Serial output from the Cycle Analyst
    - Amp-hours
    - Voltage
    - Current
    - Speed
    - Distance
- Adafruit Featherwing GPS (Mercator projection)
    - GPS fix
    - GPS X
    - GPS Y
- Analog Readings
    - Throttle
    - Brake
    - Motor Temperature
    - 4 Battery Temperatures
- Adafruit 10DOF IMU
    - Ambient Temperature
    - Roll
    - Pitch
    - Heading
    - Altitude

Another ESP32 receives the message and passes it to a computer. The computer then hosts a web page and Wi-Fi hotspot that provides a live dashboard of the data.

### Assembling the PCB

Published PCB designs with instructions are coming soon. If you are interested in replicating our system, please contact a team member at [contact@hhsevgp.org](mailto:contact@hhsevgp.org).

## Running the System

### Software Requirements

To program both ESP32s, you need the Arduino IDE with the following libraries:
- `7Semi-ADS1xx5`
- `Adafruit 10DOF`
- `Adafruit GPS Library`
- `ArduinoJson`
> Be sure to install all dependencies when prompted

On the Base Station, create a Python virtual environment and install the following with pip:
- `pyserial`
- `flask`
- `flask-sse`
- `redis`
- `gevent`
- `gunicorn`

Additionally, you need to install Redis with apt:

    sudo apt install redis

### Starting the car

After the PCB is assembled, everything is wired properly, and the ESP32 is programmed, the data system should just start up once powered.

The white light indicates power, the red light indicates an error, and the green light indicates a data point was logged.

> Note: For accurate measurements, the electrical systems of the board and the car need to share a common ground. This can be done by running a wire from the ground of the motor controller and soldering it to a ground pad of the barrel jack. A dedicated ground terminal will be added to next year's board.

### Starting the Base Station

The easiest way to get started is to clone the repository:

    git clone https://github.com/HHS-EVGP/Radio-Telemetry.git

Next you need to set up the Python environment.

    cd Radio-Telemetry
    python -m venv pyenv
    source pyenv/bin/activate
    pip install pyserial flask flask-sse redis gevent gunicorn

At this point, if you are using Linux, you can simply run the startup script. Make sure that you specify your hotspot information (`IFACE`, `SSID`, and `PASSWRD`) in `BaseStation/wifiConfig.sh`, set `RANDOM_DATA = False` at the top of `BaseStation/station.py`, and plug in the programmed receiver ESP32.

    BaseStation/startup.sh

Now the server should be running, and you can go to its IP address on **port 5000** in a web browser. Some example addresses include:

- `127.0.0.1:5000` (localhost)
- `10.42.0.1:5000` (default NetworkManager hotspot IP)
- `192.168.0.143:5000`

If you have issues connecting from another device, check your firewall rules.

### Running on other platforms
This system has only been tested on Linux Mint 22.3 (based on Ubuntu 24.04), but it should, in theory, work on any platform as long as you install all the aforementioned dependencies and do not use the startup script. For reference, here is what the startup script does:

- Creates a Wi-Fi hotspot using NetworkManager (this can be done through most system settings or skipped)
- Starts the Redis server (you will have to figure out how to install this on your own)
- Starts the web server and station Python programs (if you have a properly set up virtual environment, this should just work)

## Acknowledgements

Special thanks to GlobalEEE and all event sponsors.

*This project is licensed under the MIT license.*
