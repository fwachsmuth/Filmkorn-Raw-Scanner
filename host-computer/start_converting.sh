#!/bin/bash --login
# This script shall be launched on the host computer, not on the Raspi.
# It starts the watchdog and conversion process to turn Scanner Raw Files to DNG and then CinemaDNG.

# call this from the raspi like 
# ssh -i ~/.ssh/id_filmkorn-scanner_ed25519 `cat .user_and_host` "{host_path}/start_converting.sh"

cd "$(dirname -- "$0")/helper"
exec python3 cineDNG_creator.py -i "`cat ../.scan_destination`/raw-intermediates/" -o "`cat ../.scan_destination`/CinemaDNG/." --cinema-dng --keep-running
