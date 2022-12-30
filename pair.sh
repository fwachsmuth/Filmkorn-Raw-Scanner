#!/bin/bash

# Generate and deploy a keypair to control the scanning Raspi
ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C scanning-`whoami`@`hostname -s` -N ''

# Configure this computer for easy & secure ssh to the Raspi, if it isn't yet
if ! grep -q filmkorn-scanner.local ~/.ssh/config; then
  cat <<EOT >> ~/.ssh/config
Host filmkorn-scanner.local
  IdentityFile ~/.ssh/id_filmkorn-scanner_ed25519
  StrictHostKeyChecking no
EOT
fi

# To do: Use sesame key for ssh-copy and delete it afterwards
echo "Please enter the temporary Raspi password "filmkorn-rocks" to allow pairing."
ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub pi@filmkorn-scanner.local


# On the Raspi, generate and deploy a keypair to send files to this computer
ssh pi@filmkorn-scanner.local "ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C pi@filmkorn-scanner -N ''"
echo ""
echo "Please enter the password of this Mac to allow receiving scanned film frames going forward."
echo ""
ssh pi@filmkorn-scanner.local -t "ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub `whoami`@`hostname -s`.local"

echo ""
echo "Pairing complete!"
echo ""
