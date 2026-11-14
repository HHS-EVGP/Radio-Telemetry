#!/bin/bash

# Move to the root folder of the project
cd "$(dirname "$0")/.."
source BaseStation/wifiConfig.sh # This defines IFACE, SSID, and PASSWRD

# You can set your own hotspot parameters here
#SSID=""
#PASSWRD=""
#IFACE=""

# Stop the webserver and hotspot when the script ends
cleanup() {
	echo "Stopping webserver..."
	[ -n "$GUNICORN_PID" ] && kill "$GUNICORN_PID" 2>/dev/null

	echo "Turning off hotspot..."
	nmcli connection down Hotspot
	nmcli connection delete Hotspot
}
trap cleanup EXIT

# Clear any hotspot connection and create a new one
nmcli connection delete Hotspot 2>/dev/null
nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASSWRD"

# Activate the python environment
source ./pyenv/bin/activate

# Start the redis server if needed
if [ "$(redis-cli ping)" != "PONG" ]; then
	redis-server --daemonize yes
fi

# Start the webserver in the background and station.py in the foreground
gunicorn -k gevent -w 2 --worker-connections 1000 BaseStation.frontend.webserver:app -b 0.0.0.0:5000 &
GUNICORN_PID=$!
python BaseStation/station.py
