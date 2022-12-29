#!/bin/bash

# Remove lines from authorized_keys and known_hosts locally
echo "Asking Raspi to unpair..."
ssh pi@filmkorn-scanner.local "cd Filmkorn-Raw-Scanner/raspi; ./unpair-from-client.sh"

echo "Removing Raspi from this Computer's known_hosts..."
ssh-keygen -R filmkorn-scanner.local
echo "Removing Raspi from this Computer's authorized_keys..."
sed -i '' '\#pi@filmkorn-scanner#d' ~/.ssh/authorized_keys # extra quotes for BSD sed...

# Remove local keypairs
echo "Removing keypair from this computer..."
rm ~/.ssh/id_filmkorn-scanner_ed25519*

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
