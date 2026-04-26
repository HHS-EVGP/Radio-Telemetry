#!/bin/bash
source config.sh # This defines IFACE, SSID, and PASSWRD

# Clear any hotspot connection and create a new one
nmcli connection delete Hotspot
nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASSWRD"

# Start the server
../pyenv/bin/python station.py

# Stop the hotspot when the script ends
trap '
echo "Turning off hotpost..."
nmcli connection down Hotspot
nmcli connection delete Hotspot
' SIGINT SIGTERM EXIT