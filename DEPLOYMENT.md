# Translator Bot — installation and operation

The guide for people *using* the bot is [README.md](README.md). This file is the
server side: installing from scratch, migrations, systemd, nginx.

A Telegram bot that translates group messages automatically, plus a web admin
panel.

Two values appear throughout this guide and in the files under `deploy/`.
Replace both with your own:

- `/opt/translator-bot` — the directory you install the project into.
- `example.com` — the domain the web panel answers on.

## What the server needs

- Linux with systemd. The guide is written for Debian/Ubuntu; package names
  differ on other distributions.
- Python 3.12 or newer.
- PostgreSQL 14 or newer.
- nginx and a TLS certificate for your domain, if you want the web panel
  reachable from outside. The bot itself needs no public port at all — it uses
  long polling.
- Fonts and OCR, for file and image translation:

```bash
sudo apt install python3-venv postgresql nginx \
  fonts-dejavu-core fonts-noto-core fonts-noto-cjk \
  tesseract-ocr tesseract-ocr-all
```

About those packages:

- `fonts-dejavu-core` provides the font at
  `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, needed when rebuilding
  translated PDFs. Without it the bot sends the translation as text and says
  why.
- `fonts-noto-core` and `fonts-noto-cjk` are for drawing translations over
  images in non-Latin scripts. If Pillow has `raqm`, Arabic and Devanagari are
  shaped correctly rather than merely drawn.
- `tesseract-ocr-all` means 161 languages, roughly 667 MB in
  `/usr/share/tesseract-ocr/5/tessdata/`. If space matters, install only the
  models you need plus `osd`. The bot first detects the script with `osd`, then
  reads with a single model: the chat's language if it matches that script,
  otherwise the script model (`Latin`, `Cyrillic`, `HanS`, `Arabic`). Sticking
  to one model matters for speed — `ron` is 2.4 MB and takes about 3 seconds,
  `Latin` is 89 MB, and two models combined climb to around 10 seconds.

  Script models may be listed by Tesseract either bare (`Latin`) or under a
  prefix (`script/Latin`), depending on how tessdata is laid out. The bot
  accepts both, and logs when a detected script has no installed model rather
  than silently falling back.

## Architecture in brief

- `bot/` — the Telegram bot. Long polling, no public endpoint.
- `webpanel/` — a FastAPI admin panel, served by uvicorn on `127.0.0.1:8000`
  and exposed through nginx.
- `shared/` — common code: config, DB connection, password hashing (argon2),
  language detection (lingua-py), translation, and the shared lockout store.
- Both services read the same set of secrets and connect to the same PostgreSQL
  database.
- Secrets are not kept in cleartext on disk in production: they are encrypted
  with `systemd-creds` (host-bound key) and decrypted into memory only, at each
  service's start.

## Installation

### 1. Put the code on the server and build the virtualenv

```bash
sudo mkdir -p /opt/translator-bot
sudo chown "$USER" /opt/translator-bot
tar xzf translator-bot.tar.gz --strip-components=1 -C /opt/translator-bot

cd /opt/translator-bot
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

### 2. Create the database

```bash
sudo -u postgres createuser translator_bot
sudo -u postgres createdb -O translator_bot translator_bot
sudo -u postgres psql -c "ALTER ROLE translator_bot PASSWORD 'pick-a-long-random-password-here';"
```

The password you choose here goes into `DATABASE_URL` in step 4.

### 3. Create a bot in Telegram and get its token

Talk to [@BotFather](https://t.me/BotFather) in Telegram:

1. `/newbot`, follow the instructions, and you get a `TELEGRAM_BOT_TOKEN`.
2. **Required**: `/setprivacy`, pick your bot, then **Disable**. Without this
   step Telegram only sends the bot commands and direct mentions, not ordinary
   group messages, so translation would not work at all.
3. The bot does not need to be an administrator in groups. Ordinary membership
   is enough — it uses `get_chat_member` and `leave_chat`, both available to
   any member.

### 4. Create the `.env` file

```bash
cp /opt/translator-bot/.env.example /opt/translator-bot/.env
chmod 600 /opt/translator-bot/.env
```

Then edit it and fill in:

- `TELEGRAM_BOT_TOKEN` — from BotFather (step 3).
- `DATABASE_URL` — with the password from step 2:
  `postgresql+asyncpg://translator_bot:YOUR_PASSWORD@127.0.0.1:5432/translator_bot`
- `SESSION_SECRET_KEY` — generated randomly, never hardcoded:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- `API_KEY_ENCRYPTION_KEY` — a second key, generated the same way, and
  **separate from the session key**. The Fernet key that encrypts users' API
  keys is derived from it. It is required: the services refuse to start without
  it.

  The two are separate on purpose. `SESSION_SECRET_KEY` signs session cookies
  and can be rotated whenever you like — the only effect is that signed-in
  admins are logged out. `API_KEY_ENCRYPTION_KEY` **cannot** be rotated: change
  it and every stored API key becomes unreadable, and every user has to run
  `/setapikey` again. The bot checks this at startup and logs how many stored
  keys it can no longer read.

- `TRUSTED_PROXIES` — comma-separated addresses or CIDR ranges allowed to set
  `X-Forwarded-For`. Default `127.0.0.1,::1`, which is right when nginx runs on
  the same host. Anything arriving from an address not on this list is treated
  as the client itself, so a direct caller cannot forge its own address and
  slip past the per-IP lockout.
- `PANEL_ALLOWED_HOSTS` — comma-separated `Host` header values the panel will
  answer to, e.g. `example.com,www.example.com`. Leave it as `*` to disable the
  check.
- `PANEL_HOST` / `PANEL_PORT` — where the panel binds. These are read by the
  application itself, so what you set here is what is actually listened on.

There is no shared translation API key: every user brings their own through
`/setapikey`, so there is nothing to put in `.env` for that.

> **Upgrading an existing install that had no `API_KEY_ENCRYPTION_KEY`?**
> Earlier versions silently fell back to `SESSION_SECRET_KEY`. To keep the
> stored keys readable, set `API_KEY_ENCRYPTION_KEY` to the *current* value of
> `SESSION_SECRET_KEY` before restarting, and only then rotate the session key
> if you want to. Startup logs how many keys it could not decrypt, so you will
> know immediately if you got it wrong.

### 5. Run the migrations

```bash
cd /opt/translator-bot
source venv/bin/activate
set -a; source .env; set +a
alembic upgrade head
```

For future schema changes: `alembic revision --autogenerate -m "..."` then
`alembic upgrade head`.

### 6. Create your owner account for the web panel

```bash
cd /opt/translator-bot
source venv/bin/activate
set -a; source .env; set +a
python scripts/create_admin.py
```

It asks for a username and a password (both validated: no spaces, password at
least 16 characters), hashes them with argon2 and stores them in the
`admin_users` table. This account is entirely separate from bot user accounts.

### 7. Create the system user and install the systemd units

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin translatorbot
sudo chown -R translatorbot:translatorbot /opt/translator-bot
sudo chmod 755 /opt/translator-bot
```

Edit `deploy/systemd/translator-bot.service` and
`deploy/systemd/translator-panel.service` if you installed somewhere other than
`/opt/translator-bot`, then:

```bash
sudo cp deploy/systemd/translator-bot.service /etc/systemd/system/
sudo cp deploy/systemd/translator-panel.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Both units set `ProtectHome=read-only`. If you install the project anywhere
under `/home`, change that setting or move the project, or the services will
not start.

### 8. Encrypt `.env` with systemd-creds

```bash
/opt/translator-bot/scripts/encrypt_env.sh
```

This creates `/etc/translator-bot/env.cred`, encrypted with a key bound to your
server, owned `root:root`, mode `600`. Both systemd services read it from there
and decrypt it into memory only, at start. Once you have confirmed the services
come up (next step), delete the cleartext file:

```bash
rm /opt/translator-bot/.env
```

Because the encryption key is host-bound, `env.cred` is not portable: on
another server, rebuild `.env` and run `encrypt_env.sh` again.

### 9. Configure nginx

Edit `deploy/nginx/translator-panel.conf`, replace `example.com` with your
domain and `/opt/translator-bot` with the real path, then:

```bash
sudo cp deploy/nginx/translator-panel.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/translator-panel.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

The config listens on 443. If that port is already taken on your server, change
`listen` in both places and reach the panel with the port in the URL.

Security headers are set by the application, on every response it serves, so
nginx does not repeat them — duplicated headers are at best noise and at worst
ambiguous. The one exception is `location /static/`, which nginx serves
directly without going through the app, and which therefore carries its own
small set.

### 10. Start the services

```bash
sudo systemctl enable --now translator-bot.service
sudo systemctl enable --now translator-panel.service
sudo systemctl status translator-bot.service translator-panel.service
```

Follow the logs if something does not start:

```bash
journalctl -u translator-bot.service -f
journalctl -u translator-panel.service -f
```

### 11. Check it works

- Web panel: `https://example.com/login`. Sign in with the account from step 6.
- Bot: find it in Telegram by username, send `/start`, and create a user
  account (username and password, separate from the panel's admin account).
- Add the bot to a group where you are an administrator, then authenticate when
  it messages you privately.

## Operation

Running migrations on a system where `.env` has already been deleted and the
secrets live in `env.cred`: see `deploy/run_migration.txt`.

Rotating the Telegram token: `sudo scripts/rotate_bot_token.sh`. The script
decrypts `env.cred` into a temporary file, replaces the `TELEGRAM_BOT_TOKEN`
line, re-encrypts to a temporary file and moves it into place only on success,
`shred`s the cleartext, and restarts the service.

## How it works, in brief

- **Account registration**: `/start` in a private chat with the bot, then a
  username (5–20 characters, no spaces, unique) and a password (at least 16
  characters, no spaces). The password message is deleted from the chat
  immediately and never stored in cleartext — only an argon2 hash.
- **Adding to a group**: the bot checks whether whoever added it is an admin;
  if not, it leaves. If so, it asks for authentication in private (username +
  password), at most 3 attempts, otherwise it leaves the group.
- **Group language**: after authentication the admin picks the main language
  directly, or "auto" — the bot then reads the next ~20 messages without
  translating, works out the dominant language, and sets it. The vote tally is
  updated under a row lock, so simultaneous messages cannot lose each other's
  votes.
- **Translation**: for each message the language is detected locally
  (lingua-py). If local confidence is low — short or ambiguous messages, very
  common in chat — a cheap call goes to the user's provider purely to identify
  the language, not to translate. If the language differs from the group's main
  one, the message is translated and posted as a reply to the original.
  Translations longer than one Telegram message are split across several.
- **Daily limit**: set from the panel, applied globally, and reset
  automatically at midnight (server time) — no separate job, the counter is
  keyed by calendar date in the database.
- **Reactivation after losing admin**: every 10 minutes the bot checks whether
  the admin who authenticated a group is still an admin there. If not, it
  disables translation and tells them privately. Any current admin of the group
  can run `/reauthenticate` in the group to link it to their own account.
- **Announcements**: from the panel's Announcements section, an admin writes
  text (multiple lines are fine) which is sent as a private Telegram message to
  every registered account (not to groups). The bot checks every minute for
  undelivered announcements. Each delivery's outcome is committed on its own,
  so a failure partway through a run cannot un-record the messages already
  sent and cause them to be delivered twice. A new account receives, at
  registration, only the most recent announcement that existed at that moment,
  not the older ones.
- **API keys**: there is no shared key. Every translation uses a real key
  supplied by a user through `/setapikey`. In a group the sender's key is used
  if they have one, otherwise the key of the admin who authenticated the group;
  in private you need your own. If there is no key at all, the bot says once in
  the group what needs doing and then stays quiet. The daily limits (global,
  per group, per files, per images) remain, but they are usage ceilings rather
  than cost ceilings, and apply to any translation.
- **Provider failures**: a genuine credential rejection (HTTP 401/403) is the
  only thing that tells the key's owner their key did not work. Timeouts, 5xx
  responses and malformed replies are reported as a temporary failure instead,
  so nobody is pushed into replacing a perfectly good key over an outage.
  Requests are retried with backoff on connection errors and on 429/5xx, and
  the timeout scales with how much output was asked for.
- **Image translation**: off by default for every new group, turned on from the
  images section of `/filesettings`. The admin picks the maximum size, the
  reply mode (text, the picture with the translation drawn over it, or both),
  and whether images draw on the group's limit or have their own counter. Text
  is read with Tesseract, straight from memory over stdin, with no temporary
  file. If OCR confidence is under 60, the reply says the extracted text may be
  inexact. When overlaying, the translation is drawn over the original
  position, on a semi-transparent rectangle, with the font shrunk until it
  fits.
- **File translation**: off by default for every new group. The admin who
  authenticated the group turns it on from `/filesettings`, in private with the
  bot, and chooses the accepted file types (`.txt`, `.pdf`, `.docx`, `.srt`),
  the maximum size in MB, the reply mode (text in the chat, or a rebuilt file
  sent back) and whether files draw on the group's daily limit or have their
  own counter. If the admin has several groups, the bot asks which group the
  settings are for first. The same menu configures the private chat with the
  bot, where it asks which language to translate the file into. Text is
  extracted in memory (pypdf, python-docx, srt), split into chunks and
  translated with the sender's active provider — their personal key if they
  have one, otherwise the key of the admin who authenticated the group. For
  `.docx`, text inside tables, headers and footers is extracted too, not just
  body paragraphs. For `.srt` only the text lines are translated; indices and
  timings are untouched. Plain-text and subtitle files are decoded by sniffing
  the byte-order mark and falling back through UTF-8 and CP1252, and a file
  whose encoding cannot be determined is refused with a clear message rather
  than translated into mojibake. Files never touch the disk, neither on upload
  nor on rebuild.
- **Deleting an account from the panel**: the Users section's "Delete" link
  leads to a confirmation page that spells out exactly what disappears. The
  account, its encrypted API key, the feedback it sent and its announcement
  delivery records are removed. Groups it authenticated are **not** deleted:
  they stay in the database with their language and settings, but ownerless and
  deactivated, so the rest of the group does not lose its configuration. Any
  current admin reactivates one with `/reauthenticate`. Deletion is
  irreversible and only happens over POST, from the confirmation page.
- **Feedback**: `/feedback` in private with the bot (an existing account is
  required) sends a free-form message, stored and visible in the panel's
  Feedback section.

## Project layout

```
bot/                  - the Telegram bot (long polling)
  handlers/
  main.py
webpanel/              - the FastAPI admin panel
  __main__.py           - entry point: python -m webpanel
  routes/
  templates/            - semantic, screen-reader-friendly HTML
  static/
shared/                 - common code (config, DB, security, translation)
  providers/             - adapters for personal keys (Anthropic, OpenAI, ...)
  files/                  - extracting, chunking and rebuilding files
  images/                  - OCR and drawing translations over images
migrations/             - Alembic migrations
scripts/
  create_admin.py        - creates the panel's owner account
  encrypt_env.sh          - encrypts .env with systemd-creds
  rotate_bot_token.sh      - changes the Telegram token and restarts the bot
deploy/
  systemd/                - unit files for both services
  nginx/                   - nginx config for the web panel
```

## Accessibility (the bot's messages)

Users read the bot through Unigram with a screen reader, where lists and
buttons are not accessible. So the bot uses **no buttons at all** — not inline,
not reply keyboards, not link buttons. Everything that would once have been a
button is a question you answer with an ordinary word: the group's language
(`/setlanguage spanish`, `/setlanguage auto`), the provider at `/setapikey`
("openai"), the group and settings at `/filesettings` ("alpha", then "size",
then "10"). There is no `CallbackQueryHandler` in the code, and the bot does
not request `callback_query` updates.

Messages are flowing text in short paragraphs: no bullets, no one-item-per-line
layouts, no "Label: value" lines. Enumerations sit inside the sentence, with
"and" for a list (".txt, .pdf and .srt") and "or" for a choice ("Send types,
size, output, limit, on or done").

## Accessibility (web panel)

Built to screen-reader requirements: a single `<h1>` per page with a logical
heading hierarchy, `<label for>` on every form field, buttons with descriptive
text, full keyboard navigation with visible focus (`:focus-visible`), errors
and confirmations announced as text rather than by colour alone, tables with
proper column and row headers, no content that blinks or moves on its own, and
a "Skip to main content" link for fast keyboard navigation.

## Security

- Passwords (both users and panel owners) are hashed with argon2, never
  compared or stored in cleartext.
- `.env` never reaches git (`.gitignore`); in production it is encrypted on
  disk with `systemd-creds` and decrypted into memory only, per service.
- The panel's session key and the database password are generated randomly at
  install time, never hardcoded.
- Stored API keys are encrypted with a Fernet key derived per user from
  `API_KEY_ENCRYPTION_KEY`, which is a required setting and separate from the
  session key, so rotating the session key cannot destroy stored keys and a
  leak of one secret does not compromise the other.
- All requests to the panel go over HTTPS (nginx, Let's Encrypt certificate).
- The panel sets its own `Content-Security-Policy` (no scripts permitted at
  all — it ships none), `X-Frame-Options`, `X-Content-Type-Options`,
  `Referrer-Policy`, `Strict-Transport-Security`, `Permissions-Policy` and
  `Cross-Origin-Opener-Policy` on every response, so the headers hold however
  it is served rather than depending on the reverse proxy being configured
  correctly.
- Every state-changing route is behind a CSRF check and an authentication
  check; the session is cleared before sign-in to prevent session fixation.
- Both services run as a dedicated unprivileged system user with systemd
  hardening (`ProtectSystem=strict`, `NoNewPrivileges`, empty capability set,
  and so on).

## Limits and defences

A few things worth knowing when you run this in production:

- **Authentication**: after 5 failed attempts on the same username, the account
  is locked for 5 minutes, then 10, 20, 40 and so on up to 24 hours. The same
  rule applies separately to the Telegram user making the attempt (after 10
  failures) and, on the web panel, on two thresholds: 5 failures per username
  and 10 per IP address.

  The counter lives in the `login_attempts` table, not in process memory, so
  the bot, the panel and any number of panel workers all draw on one budget
  rather than one each, and a restart does not hand an attacker a fresh set of
  attempts. Counting is a single atomic upsert, so simultaneous failures
  increment rather than overwrite each other. The bot prunes rows that are
  neither locked nor recent once an hour. Every failure is logged with
  `logger.warning`.

- **Forwarded addresses**: `X-Forwarded-For` is honoured only when the
  immediate peer is listed in `TRUSTED_PROXIES`, and only its last entry — the
  one our own proxy appended. Everything before that came from the caller.
  Without this an attacker reaching the app directly could send a fresh header
  on every attempt and never fill a per-IP bucket.
- **Files**: one file may not exceed 60 API calls (`MAX_BATCHES_PER_FILE` in
  `bot/constants.py`), and one image 20. The daily quota is consumed
  proportionally — one call, one unit — and refunded if the translation fails.
  Extraction refuses more than 400,000 characters, more than 500 PDF pages, and
  `.docx` archives that inflate more than 150× their size on disk.
- **Truncated translations**: the output token budget scales with the length of
  the input rather than being a fixed number, and the reply is checked for
  having been cut off (`stop_reason` / `finish_reason`). A truncated
  translation is reported as a failure instead of being handed back as though
  it were complete.
- **Concurrency**: the bot processes up to 32 updates at once
  (`MAX_CONCURRENT_UPDATES`), so one large file no longer blocks everybody.
  A single user cannot translate two files at the same time.
- **nginx rate limits**: 5 requests/minute on `/login`, 60/minute elsewhere,
  at most 20 simultaneous connections per IP.
- **systemd resource limits**: the bot has `MemoryMax=2G` and `CPUQuota=200%`,
  the panel `MemoryMax=512M` and `CPUQuota=50%`. If the bot is OOM-killed on
  large files or on OCR, this is where you raise it.
- **Target language** is validated against the ISO 639-1 list in
  `shared/languages.py` before it reaches the system prompt. Anything else is
  refused, so nobody can turn the bot into a general-purpose LLM on someone
  else's key.
- **Blocking a user** from the panel now stops everything: a handler that runs
  before all others drops updates from blocked accounts, a blocked user's key
  no longer funds any group, and groups they own are deactivated at the next
  periodic check.
