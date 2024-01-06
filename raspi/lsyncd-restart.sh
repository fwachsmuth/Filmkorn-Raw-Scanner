#!/bin/bash
# to be run on the raspi, not on the host computer!
# This script usually gets called by update-destinations.sh

echo "Killing lsyncd..."
kill `cat /tmp/lsyncd.pid`
echo "Waiting..."
sleep 1
echo "Starting lsyncd..."
lsyncd /home/pi/Filmkorn-Raw-Scanner/raspi/lsyncd.conf
