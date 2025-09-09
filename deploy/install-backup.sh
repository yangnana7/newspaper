#!/usr/bin/env bash
set -Eeuo pipefail

# Install T8 backup/verify scripts and timers into system
# Requires sudo/root

echo "[INFO] Installing newshub backup/verify components"

# 1) Directories and permissions
install -o root -g postgres -m 0770 -d /var/backups/newshub
install -o root -g postgres -m 0770 -d /var/backups/newshub/app
# ensure setgid so files inherit group 'postgres'
chmod 2770 /var/backups/newshub /var/backups/newshub/app

# 2) Scripts
install -o root -g root -m 0755 scripts/newshub-backup.sh /usr/local/bin/newshub-backup.sh
install -o root -g root -m 0755 scripts/newshub-verify.sh /usr/local/bin/newshub-verify.sh

# 3) systemd units
install -o root -g root -m 0644 deploy/newshub-backup.service /etc/systemd/system/newshub-backup.service
install -o root -g root -m 0644 deploy/newshub-backup.timer /etc/systemd/system/newshub-backup.timer
install -o root -g root -m 0644 deploy/newshub-verify.service /etc/systemd/system/newshub-verify.service
install -o root -g root -m 0644 deploy/newshub-verify.timer /etc/systemd/system/newshub-verify.timer

systemctl daemon-reload
systemctl enable --now newshub-backup.timer newshub-verify.timer

echo "[OK] Installed. Use: systemctl list-timers | egrep 'newshub-(backup|verify)'"
