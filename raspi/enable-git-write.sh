#!/bin/bash
# to be run on the raspi, not on the host computer!

# This script is called from remote by opme.sh, after pairing. 

cd ~/Filmkorn-Raw-Scanner
git remote set-url origin git@github.com:fwachsmuth/Filmkorn-Raw-Scanner.git
git config --global user.email "me@peaceman.de"
git config --global user.name "Friedemann Wachsmuth"
if ! grep -q id_filmkorn-scanner-dev_ed25519 ~/.ssh/config; then
    cat <<EOT >> ~/.ssh/config
Host github.com
  HostName github.com
  IdentityFile ~/.ssh/id_filmkorn-scanner-dev_ed25519
EOT
  chmod 600 ~/.ssh/config
fi
