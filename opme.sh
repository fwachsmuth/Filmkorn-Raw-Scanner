#!/bin/bash
scp id_filmkorn-scanner-dev_ed25519* pi@filmkorn-scanner.local:~/.ssh
ssh pi@filmkorn-scanner.local "cd Filmkorn-Raw-Scanner; git remote set-url origin git@github.com:fwachsmuth/Filmkorn-Raw-Scanner.git"
