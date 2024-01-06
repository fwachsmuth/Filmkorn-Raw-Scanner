#!/bin/bash
# to be run on the raspi, not on the host computer!
# This script should be run before a new raspi image gets created.

echo "Cleaning up..."
rm ~/.ssh/knwon_hosts
rm ~/.ssh/knwon_hosts.old
rm ~/.ssh/authorized_keys
rm ~/.ssh/id_filmkorn-scanner_ed25519*
# Todo: remove git key