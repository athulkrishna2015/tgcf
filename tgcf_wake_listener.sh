#!/bin/bash
# tgcf Wake-from-Sleep Listener Daemon
# Listens to DBus suspend/resume events and runs tgcf past mode on system wake.

echo "$(date): Starting tgcf wake listener daemon..."

dbus-monitor --system "type='signal',interface='org.freedesktop.login1.Manager',member='PrepareForSleep'" 2>/dev/null | \
while read -r line; do
    if echo "$line" | grep -q "boolean false"; then
        echo "$(date): Wake-from-sleep event detected. Executing tgcf..."
        cd /mnt/0946E88701BE265B/portable/tgcf/who
        flock -n tgcf.lock .venv/bin/tgcf past --resilient --loud >> cron.log 2>&1
        echo "$(date): tgcf execution complete/yielded."
    fi
done
