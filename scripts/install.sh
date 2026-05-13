#!/usr/bin/env bash
# Provision the Kalshi Maker Bot on a fresh Hetzner CX22 (Ubuntu 24.04).
# Run as root.  Idempotent.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

APP_USER="kalshibot"
APP_HOME="/opt/kalshi-maker-bot"
ETC_DIR="/etc/kalshi-maker-bot"
DATA_DIR="/var/lib/kalshi-maker-bot"
LOG_DIR="/var/log/kalshi-maker-bot"

apt-get update
apt-get install -y --no-install-recommends \
  python3.12 python3.12-venv python3-pip git ca-certificates

id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_HOME" --shell /usr/sbin/nologin "$APP_USER"

install -d -o "$APP_USER" -g "$APP_USER" -m 0755 "$APP_HOME"
install -d -o root -g "$APP_USER" -m 0750 "$ETC_DIR"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$DATA_DIR"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$LOG_DIR"

if [[ ! -d "$APP_HOME/.git" ]]; then
  echo "Clone the repo into $APP_HOME first, then re-run this script." >&2
  exit 2
fi

cd "$APP_HOME"
sudo -u "$APP_USER" python3.12 -m venv .venv
sudo -u "$APP_USER" .venv/bin/pip install --upgrade pip
sudo -u "$APP_USER" .venv/bin/pip install -e .

if [[ ! -f "$ETC_DIR/.env" ]]; then
  install -o root -g "$APP_USER" -m 0640 .env.example "$ETC_DIR/.env"
  echo "Wrote default $ETC_DIR/.env from .env.example.  Edit before starting the service."
fi

install -o root -g root -m 0644 systemd/kalshi-maker-bot.service /etc/systemd/system/
systemctl daemon-reload

echo "Done.  Next steps:"
echo "  1. Edit $ETC_DIR/.env (MODE=sim, fill Kalshi + Sheets creds)."
echo "  2. Place RSA key at $ETC_DIR/kalshi_private_key.pem (mode 0600, owner $APP_USER)."
echo "  3. Place Google creds at $ETC_DIR/google-credentials.json (mode 0640)."
echo "  4. systemctl enable --now kalshi-maker-bot.service"
echo "  5. journalctl -u kalshi-maker-bot.service -f"
