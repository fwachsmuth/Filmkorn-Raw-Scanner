#!/bin/bash

# echo "Removing known_hosts..."
# rm ~/.ssh/knwon_hosts
# rm ~/.ssh/knwon_hosts.old

echo "Removing client from Raspi's authorized_keys..."
sed -i '\#scanning-#d' ~/.ssh/authorized_keys

echo "Removing client from this Computer's known_hosts..."
ssh-keygen -R filmkorn-scanner.local

# Remove local keypairs
echo "Removing keypair from Raspi..."
rm ~/.ssh/id_filmkorn-scanner_ed25519*

# Verify
echo "------------------------------------------------"
echo "Raspi's knwon_hosts:"
test ~/.ssh/known_hosts && cat ~/.ssh/known_hosts
echo "------------------------------------------------"
echo "Raspi's authorized_keys:"
test ~/.ssh/authorized_keys && cat ~/.ssh/authorized_keys
echo "------------------------------------------------"
echo "Raspi's keys:"
ls -la ~/.ssh/
echo "------------------------------------------------"
echo "Raspi's config:"
test ~/.ssh/config && cat ~/.ssh/config
echo "------------------------------------------------"

echo "Raspi finished its unpairing."
echo ""
