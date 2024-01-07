#!/bin/bash

# This script updates the destination client & path for storing the captured raw files.

helpFunction()
{
   echo ""
   echo "Usage: $0 -h user@host -p path"
   echo -e "\t-h username and name of your Mac, e.g. janedoe@macbook-pro.local" 
   echo -e "\t-p Path on your Mac where the scans shoudl go. This should have plenty of space."
   exit 1 # Exit script after printing help
}

while getopts "h:p:" opt
do
    case "$opt" in
        h ) userhost="$OPTARG" ;;
        p ) rawpath="$OPTARG" ;;
        ? ) helpFunction ;; # Print helpFunction in case parameter is non-existent
    esac
done

# Print helpFunction in case parameters are empty
if [ -z "$userhost" ] || [ -z "$rawpath" ]
then
   echo "Some or all of the parameters are empty";
   helpFunction
else
    # Todo: Add if clause catching file writes: https://stackoverflow.com/a/73460574
    cat << EOFCONFIGFILE > ~/Filmkorn-Raw-Scanner/raspi/lsyncd.conf
settings {
  logfile = "/tmp/lsyncd.log",
  statusFile = "/tmp/lsyncd.status",
  nodaemon = false,
  pidfile = "/tmp/lsyncd.pid",
  insist = true
}

sync {
  default.rsyncssh,
  source = "/mnt/ramdisk/",
  host = "${userhost}",
  targetdir = "${rawpath}/raw-intermediates",
  delete = false,
  rsync = {
    archive = true,
    compress = false,
    dry_run = false,
    rsync_path = "/opt/homebrew/bin/rsync",
    verbose = true,
    whole_file = true,
    _extra = {
      "--remove-source-files"
    }
  },
  ssh = {
    identityFile = "/home/pi/.ssh/id_filmkorn-scanner_ed25519" 
  }
}
EOFCONFIGFILE
    echo "${rawpath%/}" > ~/Filmkorn-Raw-Scanner/raspi/.scan_destination
    echo "New host: ${userhost}"
    echo "New path: ${rawpath%/}"
    ~/Filmkorn-Raw-Scanner/raspi/lsyncd-restart.sh
    echo "Configuration updated."
fi