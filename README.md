# EVGP Data Collection and Visualization System

This project is a data collection and visualization system for an electric race car using two Raspberry Pis and a CC1101 Radio module. The Pi collects data, stores it in an SQLite3 database, and transmits it to a pit station. The station stores the data in another SQLite database and visualizes it through a web interface.

### Who Are We?

The Harrisonburg High School Electric Vehicle Grand Prix team is a student-run racing team that builds an electric car and races it in an endurance race. As of 2025, we are a four-year-old team, and from the start, live data has been an important part of our race strategy.

#

### Prerequisites
There are two ends of this system: the car's Pi, which records and transmits data, and the base station's Pi, which displays and analyzes the data.

> **Virtual Environments:**
From Python 3.3 onward, virtual environments are recommended when installing libraries with pip. This is to prevent conflicts with the system package manager.

A virtual environment can be created with `python -m venv [name]`. In our code, we use the name `pyenv`.

**Once you have the virtual environment activated with `source [name]/bin/activate`, install the following:**

On the Car:
  - `adafruit-blinka`
  - `adafruit-circuitpython-busdevice`
  - `adafruit-circuitpython-ads1x15`
  - `adafruit-circuitpython-lsm6ds`
  - `pyserial`
  - `RPi.GPIO`
  - `smbus`
  - `cc1101`

On the Base Station:
  - `flask`
  - `waitress`
  - `cc1101`

#

### Running

**Running manually (from the home directory):**

On the Car: `source [envname]/bin/activate && python collector.py`

On the Base Station: `sudo ./startup.sh`

**Service files are available for running on startup**

1. Move `buttons.service` and `basestation.service` respectively to `/etc/systemd/system/`

2. Run `sudo systemctl enable [service name]` and `sudo systemctl start [service name]`

3. Ensure that the service is running with `systemctl status [service name]`

> **Note:** The car's service runs a button manager, but should still start collecting data automatically.

#

### Acknowledgements

Special thanks to GlobalEEE and all event sponsors.

*This project is licensed under the MIT license.*
