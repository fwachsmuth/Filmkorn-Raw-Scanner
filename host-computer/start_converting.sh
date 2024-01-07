#!/bin/bash --login
# This script shall be launched on the host computer, not on the Raspi.
# It starts the watchdog and conversion process to turn Scanner Raw Files to DNG and then CinemaDNG.

# call this from the raspi like 
# ssh -i ~/.ssh/id_filmkorn-scanner_ed25519 peaceman@wachsmut-mbp-2021.local "cd code/Filmkorn-Raw-Scanner/host-computer; ./start_converting.sh"

cd helper
python3 cineDNG_creator.py -i "`cat ../.scan_destination`/raw-intermediates/" -o "`cat ../.scan_destination`/CinemaDNG/." --cinema-dng --keep-running