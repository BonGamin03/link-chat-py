#!/usr/bin/env bash
# entrypoint for linkchat container
set -e

# find first non-loopback interface with a MAC
iface=""
for f in /sys/class/net/*; do
  name=$(basename "$f")
  if [ "$name" = lo ]; then
    continue
  fi
  addr_file="$f/address"
  if [ -f "$addr_file" ]; then
    mac=$(cat "$addr_file" | tr -d '\n')
    if [ "$mac" != "00:00:00:00:00:00" ] && [ -n "$mac" ]; then
      iface=$name
      break
    fi
  fi
done

if [ -z "$iface" ]; then
  echo "[entrypoint] No network interface detected inside container"
else
  echo "[entrypoint] Detected interface: $iface"
fi

# If user passed -i/--iface, don't override; otherwise pass detected iface
if [ "$1" = "-i" ] || [ "$1" = "--iface" ]; then
  exec python /app/link_chat.py "$@"
else
  if [ -n "$iface" ]; then
    exec python /app/link_chat.py -i $iface "$@"
  else
    exec python /app/link_chat.py "$@"
  fi
fi
