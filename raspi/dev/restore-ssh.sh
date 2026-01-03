#!/bin/bash
set -euo pipefail

sudo ssh-keygen -A
sudo systemctl restart ssh
sudo systemctl status ssh --no-pager
sudo passwd pi
./../pairing/unpair-from-client.sh
echo "Next: Run ./host-computer/helper/unpair.sh on your host computer to complete the unpairing."
echo "Then: Run ./host-computer/install_remote_scanning.sh on your host computer to pair again."
