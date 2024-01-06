#!/bin/bash
# tobe run on the host computer, not on the raspi!

if [ -f ".paired" ]; then
  echo "Systems already paired. Use ./unpair.sh first if you want to initiate pairing again."
else

  # Generate and deploy a keypair to control the scanning Raspi
  ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C scanning-`whoami`@`hostname -s` -N ''

  # Configure this computer for easy & secure ssh to the Raspi, if it isn't yet
  if ! grep -q filmkorn-scanner.local ~/.ssh/config; then
    cat <<EOT >> ~/.ssh/config
  Host filmkorn-scanner.local
    AddKeysToAgent no
    UseKeychain no
    IdentitiesOnly yes
    IdentityFile ~/.ssh/id_filmkorn-scanner_ed25519
    StrictHostKeyChecking no
EOT
  fi

  # To do: Use sesame key for ssh-copy and delete it afterwards
  bold=$(tput bold)
  normal=$(tput sgr0)
  echo "Please enter the temporary Raspi password ${bold}'filmkorn-rocks'${normal} to allow pairing."
  ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub pi@filmkorn-scanner.local > /dev/null 2> /dev/null

  # On the Raspi, generate and deploy a keypair to send files to this computer
  ssh pi@filmkorn-scanner.local "ssh-keygen -t ed25519 -q -f ~/.ssh/id_filmkorn-scanner_ed25519 -C pi@filmkorn-scanner -N ''"
  echo ""
  echo "When prompted, please enter the password ${bold}of this Mac${normal} to allow receiving scanned film frames going forward."
  ssh pi@filmkorn-scanner.local -t "ssh-copy-id -i ~/.ssh/id_filmkorn-scanner_ed25519.pub `whoami`@`hostname -s`.local > /dev/null 2> /dev/null"

  echo "Downloading latest Scanner Code..."
  ssh pi@filmkorn-scanner.local "test -d ~/Filmkorn-Raw-Scanner || git clone https://github.com/fwachsmuth/Filmkorn-Raw-Scanner.git"
  ssh pi@filmkorn-scanner.local "cd ~/Filmkorn-Raw-Scanner; git pull"

  echo "Configuring where on the Mac the scans should be stored..."
  ssh pi@filmkorn-scanner.local "./Filmkorn-Raw-Scanner/raspi/update-destination.sh -h `whoami`@`hostname -s`.local -p /Volumes/Filme/raw-intermediates"

  echo ""
  echo "Latest Code installed."
  echo ""
  echo "Pairing complete!"
  echo ""
  touch .paired

fi