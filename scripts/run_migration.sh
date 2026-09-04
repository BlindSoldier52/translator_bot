#!/usr/bin/env bash
# Run Alembic migrations on a server where .env has already been deleted and the
# secrets live in the systemd-creds credential. The credential is decrypted into
# a transient unit's memory, never onto disk.
#
#   sudo scripts/run_migration.sh                 # upgrade to the latest revision
#   sudo scripts/run_migration.sh "upgrade head --sql"   # dry run, prints the SQL
#   sudo scripts/run_migration.sh "downgrade -1"         # roll one revision back
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/translator-bot}"
CRED_NAME="translator-bot-env"
CRED_FILE="/etc/translator-bot/env.cred"
SERVICE_USER="${SERVICE_USER:-translatorbot}"
ALEMBIC_ARGS="${1:-upgrade head}"

if [ "$(id -u)" -ne 0 ]; then
	echo "Run this with sudo: sudo $0" >&2
	exit 1
fi

if [ ! -f "$CRED_FILE" ]; then
	echo "Cannot find $CRED_FILE. Run scripts/encrypt_env.sh first." >&2
	exit 1
fi

exec systemd-run --pty \
	--unit=translator-bot-migrate \
	-p "User=$SERVICE_USER" -p "Group=$SERVICE_USER" \
	-p "LoadCredentialEncrypted=$CRED_NAME:$CRED_FILE" \
	--working-directory="$INSTALL_DIR" \
	/bin/bash -c "set -a; source \"\$CREDENTIALS_DIRECTORY/$CRED_NAME\"; venv/bin/alembic $ALEMBIC_ARGS"
