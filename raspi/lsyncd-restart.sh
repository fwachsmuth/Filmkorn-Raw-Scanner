#!/bin/bash
# to be run on the raspi, not on the host computer!
# This script usually gets called by update-destinations.sh
echo "Restarting Killing lsyncd..."
sudo systemctl restart lsyncd
sudo systemctl status --no-pager -20 lsyncd