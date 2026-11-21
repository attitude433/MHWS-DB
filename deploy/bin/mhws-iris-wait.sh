#!/bin/bash
for i in $(seq 1 60); do
  BOOT=$(sudo docker exec redroid getprop sys.boot_completed 2>/dev/null)
  [ "$BOOT" = "1" ] && exit 0
  sleep 5
done
exit 1
