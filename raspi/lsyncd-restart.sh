#!/bin/bash
echo "Killing lsyncd..."
kill `cat /tmp/lsyncd.pid`
echo "Waiting..."
sleep 1
echo "Starting lsyncd..."
lsyncd /home/pi/Filmkorn-Raw-Scanner/raspi/lsyncd.conf
