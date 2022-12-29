#!/bin/bash

# Remove lines from authorized_keys and known_hosts locally and rmeote
echo "Removing this Computer from Raspi's known_hosts..."
ssh pi@filmkorn-scanner.local "ssh-keygen -R `hostname -s`.local"
echo "Removing this Computer from Raspi's authorized_keys..."
ssh pi@filmkorn-scanner.local "sed -i '\#`awk '{print $2}' ~/.ssh/id_filmkorn-scanner_ed25519.pub`#d' ~/.ssh/authorized_keys"
echo "Removing Raspi from this Computer's known_hosts..."
ssh-keygen -R filmkorn-scanner.local
echo "Removing Raspi from this Computer's authorized_keys..."
sed -i '' '\#pi@filmkorn-scanner#d' ~/.ssh/authorized_keys # extra quotes for BSD sed...

# Remove local and remote keypairs
echo "Removing keypair from this computer..."
rm ~/.ssh/id_filmkorn-scanner_ed25519*
echo "Removing keypair from Raspi..."
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
