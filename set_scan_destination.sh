#!/bin/bash
# to be run on the host computer, not on the raspi!

# touch "`cat host-computer/destination_path.conf`/foobar"

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
    echo "Currently configured Scan Destination: `cat .scan_destination`"
else
    echo "No Scan Destination has been configured yet."
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
        echo "Changing to ${rawpath%/}"
    else
        echo "Setting Scan Destination to ${rawpath%/}"
    fi
    echo "${rawpath%/}" > .scan_destination
else
    if [ ! -d "$rawpath" ]; then
        echo "ERROR: The path ${rawpath%/} does not seem to exist. Please check yor path and try again."
        echo "If your path contains spaces, wrap it in quotes, e.g. \"/Volumes/Macintosh HD\""
    fi
fi