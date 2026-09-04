#!/usr/bin/env bash
set -euo pipefail

CRED_NAME="translator-bot-env"
CRED_DIR="/etc/translator-bot"
CRED_FILE="$CRED_DIR/env.cred"
PLAIN_FILE="$CRED_DIR/env.plain.$$"
SERVICE="translator-bot"

if [ "$(id -u)" -ne 0 ]; then
	echo "Run this with sudo: sudo $0" >&2
	exit 1
fi

if [ ! -f "$CRED_FILE" ]; then
	echo "Cannot find $CRED_FILE" >&2
	exit 1
fi

cleanup() {
	if [ -f "$PLAIN_FILE" ]; then
		shred -u "$PLAIN_FILE"
	fi
	if [ -n "${CRED_TMP:-}" ] && [ -f "$CRED_TMP" ]; then
		rm -f "$CRED_TMP"
	fi
}
trap cleanup EXIT

echo "Paste ONLY the token: nothing else, none of the surrounding text from BotFather."
read -rsp "New Telegram token (it will not be shown): " NEW_TOKEN
echo

NEW_TOKEN="${NEW_TOKEN//$'\r'/}"
NEW_TOKEN="${NEW_TOKEN%%$'\n'*}"
NEW_TOKEN="$(printf '%s' "$NEW_TOKEN" | tr -d '[:space:]')"

if [ -z "$NEW_TOKEN" ]; then
	echo "Empty token, aborting." >&2
	exit 1
fi
if ! [[ "$NEW_TOKEN" =~ ^[0-9]{6,}:[A-Za-z0-9_-]{30,}$ ]]; then
	echo "That does not look like a valid Telegram token (expected digits:code). Paste ONLY the token and run again." >&2
	exit 1
fi

umask 077
systemd-creds decrypt --name="$CRED_NAME" "$CRED_FILE" "$PLAIN_FILE"

NEW_FILE="$PLAIN_FILE.new"
: >"$NEW_FILE"
FOUND=0
while IFS= read -r line || [ -n "$line" ]; do
	if [[ "$line" == TELEGRAM_BOT_TOKEN=* ]]; then
		printf 'TELEGRAM_BOT_TOKEN=%s\n' "$NEW_TOKEN" >>"$NEW_FILE"
		FOUND=1
	elif [ -z "$line" ] || [[ "$line" == \#* ]] || [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
		printf '%s\n' "$line" >>"$NEW_FILE"
	else
		echo "Dropping an invalid line left in the file, most likely from an earlier failed run." >&2
	fi
done <"$PLAIN_FILE"

if [ "$FOUND" -eq 0 ]; then
	printf 'TELEGRAM_BOT_TOKEN=%s\n' "$NEW_TOKEN" >>"$NEW_FILE"
fi

mv "$NEW_FILE" "$PLAIN_FILE"
unset NEW_TOKEN

CRED_TMP="$CRED_FILE.new.$$"
systemd-creds encrypt --name="$CRED_NAME" "$PLAIN_FILE" "$CRED_TMP"
chown root:root "$CRED_TMP"
chmod 600 "$CRED_TMP"
mv "$CRED_TMP" "$CRED_FILE"

shred -u "$PLAIN_FILE"
trap - EXIT

echo "Token updated in $CRED_FILE."

systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" && echo "$SERVICE restarted successfully." || {
	echo "$SERVICE did NOT start correctly. Check: journalctl -u $SERVICE -n 50" >&2
	exit 1
}

echo
echo "The old token is still exposed in the systemd journal history, from before the restart."
read -rp "Wipe the system-wide systemd journal history, irreversibly, to remove those old entries too? Type YES to confirm: " CONFIRM
if [ "$CONFIRM" = "YES" ]; then
	journalctl --rotate
	sleep 2
	journalctl --vacuum-time=2s
	echo "Journal history cleared."
else
	echo "Skipped clearing the journal. The old token, already revoked and replaced, stays visible in old logs."
fi
