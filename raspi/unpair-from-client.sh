#!/bin/bash

# echo "Removing known_hosts..."
# rm ~/.ssh/knwon_hosts
# rm ~/.ssh/knwon_hosts.old

echo "Removing client from Raspi's authorized_keys..."
sed -i '\#`awk '{print $2}' ~/.ssh/id_filmkorn-scanner_ed25519.pub`#d' ~/.ssh/authorized_keys

echo "Removing Raspi from this Computer's known_hosts..."
ssh-keygen -R filmkorn-scanner.local

# Remove local and remote keypairs
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
