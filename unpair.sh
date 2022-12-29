#!/bin/bash

# Remove lines from authorized_keys and known_hosts locally and rmeote
ssh pi@filmkorn-scanner.local "ssh-keygen -R `hostname -s`.local"
ssh pi@filmkorn-scanner.local "sed -i '\#`awk '{print $2}' ~/.ssh/id_filmkorn-scanner_ed25519.pub`#d' ~/.ssh/authorized_keys"

ssh-keygen -R filmkorn-scanner.local
sed -i '' '\#pi@filmkorn-scanner#d' ~/.ssh/authorized_keys # extra quotes for BSD sed...

# Remove local and remote keypairs
rm ~/.ssh/id_filmkorn-scanner_ed25519*
ssh pi@filmkorn-scanner.local -t "rm ~/.ssh/id_filmkorn-scanner_ed25519*"


# Verify
echo "------------------------------------------------"
echo "Local knwon_hosts:"
cat ~/.ssh/known_hosts
echo "------------------------------------------------"
echo "Local authorized_keys:"
cat ~/.ssh/authorized_keys
echo "------------------------------------------------"
echo "Local keys:"
ls -la ~/.ssh/
echo "------------------------------------------------"
echo "Local config:"
cat ~/.ssh/config
echo "------------------------------------------------"
