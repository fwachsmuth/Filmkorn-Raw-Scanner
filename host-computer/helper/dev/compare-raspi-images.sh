#!/usr/bin/env bash
# Compares two Raspberry Pi SD card images (ext4 root) inside Docker and prints
# size differences in human-readable form. Use on a Mac (or anywhere) where
# ext4 can't be mounted natively.
#
# Usage: compare-raspi-images.sh <old.img> <new.img>
# Both images must be raw .img (full disk with partitions); use gunzip -k to
# expand .img.gz first. Root partition (p2) is mounted and compared.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $(basename "$0") <old.img> <new.img>"
  echo "  Both paths must be to raw .img files (gunzip -k first if you have .img.gz)."
  exit 1
fi

OLD_IMG="$1"
NEW_IMG="$2"
for f in "$OLD_IMG" "$NEW_IMG"; do
  if [[ ! -f "$f" ]]; then
    echo "Not a file or missing: $f"
    exit 1
  fi
done

OLD_ABS="$(cd "$(dirname "$OLD_IMG")" && pwd)/$(basename "$OLD_IMG")"
NEW_ABS="$(cd "$(dirname "$NEW_IMG")" && pwd)/$(basename "$NEW_IMG")"
OLD_DIR="$(dirname "$OLD_ABS")"
NEW_DIR="$(dirname "$NEW_ABS")"

if [[ "$OLD_DIR" != "$NEW_DIR" ]]; then
  echo "Both images must be in the same directory."
  echo "  Old: $OLD_DIR"
  echo "  New: $NEW_DIR"
  exit 1
fi

MOUNT_DIR="$OLD_DIR"
OLD_BASE="$(basename "$OLD_ABS")"
NEW_BASE="$(basename "$NEW_ABS")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required."
  exit 1
fi

echo "Comparing (old) $OLD_BASE vs (new) $NEW_BASE"
echo "Mounting image directory: $MOUNT_DIR"
echo ""

docker run --rm -i --privileged \
  -v "$MOUNT_DIR:/images:ro" \
  -e OLD_IMG="/images/$OLD_BASE" \
  -e NEW_IMG="/images/$NEW_BASE" \
  debian:bookworm-slim bash -s <<'INNER'
set -euo pipefail
echo "Installing util-linux, e2fsprogs, numfmt..." >&2
apt-get -qq update && apt-get -qq install -y --no-install-recommends util-linux e2fsprogs fdisk || { echo "apt-get failed" >&2; exit 1; }

# Get partition 2 start offset (bytes) from image. Works when losetup -P partition nodes are missing (e.g. Docker on Mac).
get_p2_offset() {
  local img="$1"
  local start_sector
  # sfdisk -d: second partition line has "start= N"
  start_sector=$(sfdisk -d "$img" 2>/dev/null | grep 'start=' | sed -n '2s/.*start=[[:space:]]*\([0-9]*\).*/\1/p')
  if [[ -z "$start_sector" ]]; then
    # Fallback: fdisk -l lists partition 2 as ...img2
    start_sector=$(fdisk -l "$img" 2>/dev/null | awk '/img2[^0-9]/ {print $2; exit}')
  fi
  echo $((start_sector * 512))
}

mount_img() {
  local img="$1"
  local mnt="$2"
  local loop_dev
  loop_dev=$(losetup --show -f -P "$img" 2>/dev/null || true)
  if [[ -n "$loop_dev" ]] && [[ -b "${loop_dev}p2" ]]; then
    mount -o ro "${loop_dev}p2" "$mnt"
    echo "$loop_dev"
    return
  fi
  [[ -n "$loop_dev" ]] && losetup -d "$loop_dev" 2>/dev/null || true
  local offset
  offset=$(get_p2_offset "$img")
  loop_dev=$(losetup --show -f "$img")
  mount -o ro,offset="$offset" "$loop_dev" "$mnt"
  echo "$loop_dev"
}

LOOP_OLD=""
LOOP_NEW=""
cleanup() {
  umount -l /mnt/old /mnt/new 2>/dev/null || true
  [[ -n "$LOOP_OLD" ]] && losetup -d "$LOOP_OLD" 2>/dev/null || true
  [[ -n "$LOOP_NEW" ]] && losetup -d "$LOOP_NEW" 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p /mnt/old /mnt/new
echo "Mounting old image..." >&2
LOOP_OLD=$(mount_img "$OLD_IMG" /mnt/old)
echo "Mounting new image..." >&2
LOOP_NEW=$(mount_img "$NEW_IMG" /mnt/new)

echo "=== Top-level usage (old vs new) ==="
paste \
  <(du -sh /mnt/old/* 2>/dev/null | sort -k2 | awk '{print $1, $2}' | sed 's|/mnt/old||') \
  <(du -sh /mnt/new/* 2>/dev/null | sort -k2 | awk '{print $1, $2}' | sed 's|/mnt/new||') \
  | while read -r size_old path_old size_new path_new; do
      if [[ "$path_old" != "$path_new" ]]; then continue; fi
      if [[ "$size_old" != "$size_new" ]]; then
        echo "  $path_old: $size_old -> $size_new"
      fi
    done

echo ""
echo "=== Directories that grew (path and size change) ==="
for dir in /mnt/old/*/; do
  rel="${dir#/mnt/old}"
  new_dir="/mnt/new$rel"
  [[ -d "$new_dir" ]] || continue
  old_bytes=$(du -sb "$dir" 2>/dev/null | cut -f1)
  new_bytes=$(du -sb "$new_dir" 2>/dev/null | cut -f1)
  if [[ -n "$old_bytes" && -n "$new_bytes" && "$new_bytes" -gt "$old_bytes" ]]; then
    diff=$((new_bytes - old_bytes))
    echo "  $rel: +$(numfmt --to=iec "$diff" 2>/dev/null || echo "${diff} B")"
  fi
done

echo ""
echo "=== Items only in NEW image (depth 3, sample) ==="
comm -23 \
  <(cd /mnt/new && find . -maxdepth 3 \( -type d -o -type f \) 2>/dev/null | sort) \
  <(cd /mnt/old && find . -maxdepth 3 \( -type d -o -type f \) 2>/dev/null | sort) \
  | head -40 | while read -r p; do
  [[ -z "$p" ]] && continue
  s=$(du -sh "/mnt/new/$p" 2>/dev/null | cut -f1)
  echo "  $p ($s)"
done

echo ""
echo "=== /var breakdown (old vs new) ==="
for sub in /mnt/old/var/*/; do
  [[ -d "$sub" ]] || continue
  rel="${sub#/mnt/old}"
  new_sub="/mnt/new$rel"
  [[ -d "$new_sub" ]] || continue
  old_sz=$(du -sh "$sub" 2>/dev/null | cut -f1)
  new_sz=$(du -sh "$new_sub" 2>/dev/null | cut -f1)
  echo "  $rel: $old_sz -> $new_sz"
done
for f in /mnt/old/var/*; do
  [[ -f "$f" ]] || continue
  b=$(basename "$f")
  [[ -f "/mnt/new/var/$b" ]] || continue
  old_sz=$(du -sh "$f" 2>/dev/null | cut -f1)
  new_sz=$(du -sh "/mnt/new/var/$b" 2>/dev/null | cut -f1)
  echo "  /var/$b: $old_sz -> $new_sz"
done

echo ""
echo "=== /home breakdown (old vs new) ==="
for sub in /mnt/old/home/*/; do
  [[ -d "$sub" ]] || continue
  rel="${sub#/mnt/old}"
  new_sub="/mnt/new$rel"
  [[ -d "$new_sub" ]] || continue
  old_sz=$(du -sh "$sub" 2>/dev/null | cut -f1)
  new_sz=$(du -sh "$new_sub" 2>/dev/null | cut -f1)
  echo "  $rel: $old_sz -> $new_sz"
done
for f in /mnt/old/home/*; do
  [[ -f "$f" ]] || continue
  b=$(basename "$f")
  [[ -f "/mnt/new/home/$b" ]] || continue
  old_sz=$(du -sh "$f" 2>/dev/null | cut -f1)
  new_sz=$(du -sh "/mnt/new/home/$b" 2>/dev/null | cut -f1)
  echo "  /home/$b: $old_sz -> $new_sz"
done

echo ""
echo "=== Total root size ==="
echo "  Old: $(du -sh /mnt/old 2>/dev/null | cut -f1)"
echo "  New: $(du -sh /mnt/new 2>/dev/null | cut -f1)"
INNER
