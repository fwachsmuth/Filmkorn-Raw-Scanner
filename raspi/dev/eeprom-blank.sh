#!/bin/bash
set -euo pipefail

# Writes 0xFF to all 1024 bytes of the ATmega328P EEPROM.
# Useful for testing a blank EEPROM or recovering from corrupt data.
# Motor calibration and dotfile backup will both be lost.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BLANK=$(mktemp /tmp/eeprom-blank-XXXXXX.hex)

# Generate an Intel HEX file of 1024 x 0xFF
python3 - "$BLANK" <<'EOF'
import sys
out = sys.argv[1]
with open(out, "w") as f:
    addr = 0
    while addr < 1024:
        chunk = min(16, 1024 - addr)
        data = bytes([0xFF] * chunk)
        record = bytes([chunk, addr >> 8, addr & 0xFF, 0x00]) + data
        checksum = (-sum(record)) & 0xFF
        f.write(f":{record.hex().upper()}{checksum:02X}\n")
        addr += chunk
    f.write(":00000001FF\n")
EOF

echo "Blanking EEPROM (writing 0xFF to all 1024 bytes)..."
sudo avrdude \
  -C "${REPO_DIR}/scan-controller/avrdude_gpio.conf" \
  -p atmega328p \
  -c raspberry_pi_gpio \
  -P gpiochip0 \
  -U eeprom:w:"${BLANK}":i

rm -f "$BLANK"
echo "Done. EEPROM is now blank (all 0xFF)."
