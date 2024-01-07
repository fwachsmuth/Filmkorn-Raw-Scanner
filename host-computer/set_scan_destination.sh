#!/bin/bash
# to be run on the host computer, not on the raspi!
# This script chnages the destination base path for scan results and propagates it to all places where its needed.

# note touch "`cat host-computer/destination_path.conf`/foobar"

helpFunction()
{
   echo ""
   echo "Usage: $0 -p path"
   echo -e "\t-p Absolute path on your host computer where the scans should go. This should have plenty of space."
   echo -e "\t   You can type -p and then drag a hard drive or folder to the terminal to insert the path." 
   echo 
   exit 1 # Exit script after printing help
   echo
}
if [ -f ".scan_destination" ]; then
    echo "Currently configured Scan Destination:"
    echo
    echo "`cat .scan_destination`"
    echo
else
    echo "No Scan Destination has previously been configured yet."
fi

while getopts "p:" opt
do
    case "$opt" in
        p ) rawpath="$OPTARG" ;;
        ? ) helpFunction ;; # Print helpFunction in case parameter is non-existent
    esac
done

if [ -d "$rawpath" ] && [ ! -z "$rawpath" ]; then # Check if a path was supplied and exists
    if [ -f ".scan_destination" ]; then
        echo "Changing to" 
        echo
        echo "${rawpath%/}"
        echo
    else
        echo "Setting Scan Destination to ${rawpath%/}"
    fi
    echo "${rawpath%/}" > .scan_destination
    ssh pi@filmkorn-scanner.local "./Filmkorn-Raw-Scanner/raspi/update-destination.sh -h `whoami`@`hostname -s`.local -p \"${rawpath%/}\""
else
    if [ -z "$rawpath" ]; then
        echo "No new path has been defined."
        helpFunction    
    fi
    if [ ! -d "$rawpath" ]; then
        echo "ERROR: The path ${rawpath%/} does not seem to exist. Please check yor path and try again."
        echo "If your path contains spaces, wrap it in quotes, e.g. \"/Volumes/Macintosh HD\""
    fi
fi