#!/bin/bash

# Move to the root folder of the project
cd "$(dirname "$0")/.."
source BaseStation/wifiConfig.sh # This defines IFACE, SSID, and PASSWRD

# You can set your own hotpost parameters here
#SSID=""
#PASSWRD=""
#IFACE=""

# Clear any hotspot connection and create a new one
nmcli connection delete Hotspot
nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASSWRD"


# Activate the python enviroment
source ./pyenv/bin/activate

# Start the redis server if needed
if [ "$(redis-cli ping)" != "PONG" ]; then
	redis-server --daemonize yes
fi

# Start the webserver and station.py
gunicorn -k gevent -w 2 --worker-connections 1000 BaseStation.frontend.webserver:app -b 0.0.0.0:5000 &
python BaseStation/station.py


# Stop the hotspot when the script ends
trap '
echo "Turning off hotpost..."
nmcli connection down Hotspot
nmcli connection delete Hotspot
' EXIT
