#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$PROJECT_DIR/.env}"
CRED_NAME="translator-bot-env"
OUT_DIR="/etc/translator-bot"
OUT_FILE="$OUT_DIR/env.cred"

if [ ! -f "$ENV_FILE" ]; then
	echo "Env file not found: $ENV_FILE" >&2
	exit 1
fi

sudo mkdir -p "$OUT_DIR"
sudo systemd-creds encrypt --name="$CRED_NAME" "$ENV_FILE" "$OUT_FILE"
sudo chown root:root "$OUT_FILE"
sudo chmod 600 "$OUT_FILE"

echo "Encrypted credential written to $OUT_FILE"
echo "The plaintext file at $ENV_FILE is no longer needed by the running services."
echo "Remove it once you have verified the services start correctly:"
echo "  rm $ENV_FILE"
