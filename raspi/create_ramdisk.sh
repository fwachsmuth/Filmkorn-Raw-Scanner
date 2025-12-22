#!/bin/bash

# Calculate Ramdisk size to leave 1 GB free for the camera
total_ram=$(grep MemTotal /proc/meminfo | awk '{print $2}')
ramdisk_size=$((total_ram - 1000000)) # leave 1 GB free

# Create RAM disk
mkdir -p /mnt/ramdisk
mount -t tmpfs -o size=${ramdisk_size}k tmpfs /mnt/ramdisk
