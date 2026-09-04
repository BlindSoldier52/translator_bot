# Translation Bot

![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-3776AB?logo=python&logoColor=white)
![PostgreSQL 14+](https://img.shields.io/badge/postgresql-14%2B-4169E1?logo=postgresql&logoColor=white)
![python-telegram-bot 22.8](https://img.shields.io/badge/python--telegram--bot-22.8-26A5E4?logo=telegram&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![Accessibility: screen-reader first](https://img.shields.io/badge/accessibility-screen--reader%20first-6f42c1)
![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-green)

A Telegram bot that translates for your group chat. It watches the group, and
whenever someone writes in a language that isn't the group's main one, it
replies with a translation. It also reads text out of files and images, if the
group admin turns that on.

Everyone brings their own provider API key, so the bot costs its operator
nothing to run. It uses no buttons anywhere, because the people it was built
for read it through a screen reader.

**Using the bot?** Carry on below. **Running your own copy?** Jump to
[Quick start](#quick-start-self-hosting), or read
[DEPLOYMENT.md](DEPLOYMENT.md) for the full guide.

## Quick start (self-hosting)

The condensed path. [DEPLOYMENT.md](DEPLOYMENT.md) explains every step, the
hardening, and the things that will bite you; read it before running this
anywhere real.

**1. Dependencies.** Python 3.12, 3.13 or 3.14, PostgreSQL 14+, plus fonts and OCR:

```bash
sudo apt install python3-venv postgresql nginx \
  fonts-dejavu-core fonts-noto-core fonts-noto-cjk \
  tesseract-ocr tesseract-ocr-all
```

**2. Code and virtualenv:**

```bash
git clone https://github.com/BlindSoldier52/translator_bot.git /opt/translator-bot
cd /opt/translator-bot
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

**3. Database:**

```bash
sudo -u postgres createuser translator_bot
sudo -u postgres createdb -O translator_bot translator_bot
sudo -u postgres psql -c "ALTER ROLE translator_bot PASSWORD 'a-long-random-password';"
```

**4. Configuration.** Copy the template and fill in the four required values:

```bash
cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # run twice
```

`TELEGRAM_BOT_TOKEN` from [@BotFather](https://t.me/BotFather) — and in
BotFather run `/setprivacy` → **Disable**, or the bot never sees ordinary group
messages. `DATABASE_URL` with the password from step 3. `SESSION_SECRET_KEY`
and `API_KEY_ENCRYPTION_KEY` from the two generated values. The encryption key
is required and **can never be rotated**: change it and every stored API key
becomes unreadable.

**5. Migrate and create your panel account:**

```bash
set -a; source .env; set +a
venv/bin/alembic upgrade head
venv/bin/python scripts/create_admin.py
```

**6. Run it.** For a first look, in two terminals:

```bash
venv/bin/python -m bot           # the Telegram bot
venv/bin/python -m webpanel      # the admin panel on 127.0.0.1:8000
```

For anything permanent, use the systemd units and nginx config in `deploy/`,
and encrypt your secrets with `scripts/encrypt_env.sh` so `.env` can be deleted
from disk. DEPLOYMENT.md covers both.

**7. Try it.** Message the bot `/start` to make an account, `/setapikey` to give
it a provider key, then add it to a group you administer.

## You need your own API key

There is no shared key. The bot does not come with translation credit of its
own, so **it will not translate a single word until you give it an API key**.
That's the first thing to do after creating your account, and everything else
in this guide assumes you've done it.

You get a key from one of these providers, all of which the bot supports:

- Anthropic
- OpenAI
- OpenRouter
- xAI
- DeepSeek
- GLM

If you don't already have a favourite, OpenRouter is a sensible pick: one key
gets you at a lot of different models, so you're not tied to a single company.

In a group, the bot uses the sender's key if that person has set one. If they
haven't, it falls back to the key of the admin who set the bot up in that
group. So one admin with a key is enough to make a whole group work, and that
admin pays for it. In a private chat with the bot, you need your own key,
there's nobody to fall back on.

## Creating your account

1. Open a private chat with the bot and send `/start`.
2. Send a username when it asks. Between 5 and 20 characters, no spaces.
   Letters, numbers, dots, underscores and hyphens are fine.
3. Send a password. At least 16 characters, no spaces. The bot deletes your
   message the moment it arrives, so it doesn't sit in your chat history.
4. Save that password somewhere safe. It's hashed, which means nobody can read
   it back, and there is no way to recover it if you forget it.

You'll need the username and password again later, when you link a group.

## Adding your API key

1. In a private chat with the bot, send `/setapikey`. It only works there,
   never in a group.
2. The bot asks which provider you're using. Reply with its name, like
   `openai` or `openrouter`.
3. Paste your key as the next message. The bot deletes that message straight
   away too.
4. The bot makes one small test call to check the key really works before
   saving it. If the key is wrong or has no credit, it tells you and nothing
   is saved.
5. Send `/apikeystatus` any time to see which key you're on.
6. Send `/removeapikey` to take it off. To swap keys, just run `/setapikey`
   again and the new one replaces the old.

Careful with `/removeapikey` if you're a group admin: your key is what keeps
your groups translating, so removing it makes them go quiet.

## Adding the bot to a group

1. Make sure you're an administrator of the group. The bot checks, and if
   whoever added it isn't an admin, it leaves again immediately.
2. Add the bot to the group as a member.
3. The bot messages you privately and asks you to log in. If it can't message
   you because you've never opened a chat with it, it posts a link in the
   group instead, and you carry on from there.
4. Send your username, then your password. You get three tries. After three
   failed attempts the bot leaves the group, so if you're not sure of your
   password, stop and use `/cancel` rather than burning attempts. Failed
   attempts are remembered per account, so `/cancel` and `/reauthenticate`
   don't hand you a fresh set: after five failures in total the account is
   locked for a few minutes, and the wait doubles with each failure after
   that. Restarting the bot doesn't clear it either — the count is kept in the
   database.
5. Once you're in, the bot asks which language the group mostly speaks. Reply
   with a language name like `Spanish`, or reply `auto` and it will read the
   next twenty messages or so, work it out on its own, and tell you what it
   picked.

An admin can change that language later with `/setlanguage spanish`, or
`/setlanguage auto`, sent in the group itself.

If the bot ever deactivates itself in a group, which happens when the admin
who linked it stops being an admin there, any current admin can run
`/reauthenticate` in the group to link it again.

## How translation works day to day

Nobody has to do anything. The bot reads what goes past, and when a message
isn't in the group's main language, it replies to that message with the
translation. Messages already in the main language are left alone.

You can also ask for a translation directly. `/translate spanish hello there`
does what it looks like, and replying to someone's message with
`/translate spanish` translates just that message. Plain requests work too, so
"how do you say good morning in French" gets an answer, and a follow-up like
"now say it more informally" carries on from the last one.

The target has to be a real language, given by name or by its two-letter code.
Anything the bot doesn't recognise as a language is turned down rather than
passed along, so it stays a translator and doesn't become a general-purpose
chatbot running on somebody else's API key.

## File translation

Off by default. A group admin turns it on with `/filesettings` in a private
chat with the bot, and picks the rules for that group.

The bot can read `.txt`, `.pdf`, `.docx` and `.srt` files. With subtitles it
only touches the subtitle text, so the timings and numbering come back exactly
as they went in. In Word documents it also picks up text inside tables,
headers and footers, not just ordinary paragraphs. A plain text or subtitle
file saved in an older encoding is handled too, and if the encoding can't be
worked out the bot says so rather than handing back garbled text.

The admin decides which of those types are allowed, how big a file can be, and
whether the bot replies with the translated text in the chat or builds a new
file in the same format and sends that back.

There's a ceiling on how much text one file may contain, on top of the size
limit in megabytes. A file that would take more than sixty calls to the
translation API is turned down with a note asking you to split it up, and the
daily allowance is charged per call, not per file. That keeps one big document
from quietly spending a whole day's budget, or from making everyone else wait.

You can also use this in a private chat with the bot, with your own settings.
Send a file and the bot asks which language you want it in.

## Image translation

Also off by default, also turned on per group with `/filesettings`.

Send a photo, or an image as a file, and the bot reads the text in it and
translates it. It handles more or less any alphabet, not just Latin ones.

The admin picks one of three ways to get the result back:

- text: the bot replies with the translated text
- overlay: the bot sends the picture back with the translation drawn over the
  original text
- both: the text reply first, then the picture

In a group, images are translated into the group's main language. In a private
chat the bot asks which language you want. If the text in the picture is
blurry or hard to read, the bot says so rather than pretending the result is
exact, and if there's no readable text at all it just tells you.

## What group admins can configure

All of it lives in `/filesettings`, in a private chat with the bot. If you
manage more than one group, it asks which one first. Then you pick `files` or
`images`, and answer with plain words.

For files:

- File types: which of `.txt`, `.pdf`, `.docx` and `.srt` are allowed
- Size limit: the biggest file the bot will accept, in MB, up to 20
- Output: `text` for a reply in the chat, `file` for a translated file back
- Daily limit: `shared` to count against the group's normal daily limit, or
  `separate` to give files their own allowance
- On or off: `on` and `off` turn the whole thing on and off

For images:

- Size limit: the biggest image the bot will accept, in MB, up to 20
- Output: `text`, `overlay`, or `both`
- Daily limit: `shared` or `separate`, same as files
- On or off: `on` and `off`

Changes take effect straight away, on the very next file or image.

One thing to know about how the bot talks: it never uses buttons. Everything
is a question you answer with an ordinary word, because buttons and lists
don't read well on screen readers.

## Commands

In a private chat with the bot:

- `/start` — create your account, or say hello if you already have one
- `/help` — what the bot can do
- `/cancel` — stop whatever you're in the middle of
- `/setapikey` — give the bot the API key it translates with
- `/removeapikey` — take your key off again
- `/apikeystatus` — see which key you're on
- `/filesettings` — set up file and image translation for a group or for this chat
- `/privacy` — what the bot does with your data
- `/feedback` — send a message to the people running the bot

In a group, for admins:

- `/setlanguage` — set the group's main language, like `/setlanguage spanish` or `/setlanguage auto`
- `/reauthenticate` — link the group to your account again

In a group, for everyone:

- `/translate` — translate something, like `/translate spanish hello there`, or reply to a message with `/translate spanish`

## Privacy and data

Your password is hashed and can never be read back, by anyone. Your API key is
encrypted before it's stored, and both the password message and the key
message are deleted from the chat as soon as they arrive.

The bot doesn't keep the messages it translates. Once it has replied, all that
remains is a note that a translation happened, between which two languages,
and in which group. Files and images are handled entirely in memory and never
written to disk.

Worth being clear about: translating means sending the text to whichever AI
provider's key is in use. What that company does with it is covered by their
terms, so pick a provider you're comfortable with.

Send `/privacy` to the bot for the full version.

## Troubleshooting

**Nothing gets translated.** Nine times out of ten there's no API key. Send
`/apikeystatus` to check. In a group, either you or the admin who set the bot
up needs a working key.

**The bot says my key didn't work.** Check the key directly with your
provider: that it's still valid, that it hasn't been revoked, and that the
account has credit. Then set it again with `/setapikey`. The bot only says
this when the provider actually rejected the key — if the provider was just
slow or unreachable, it says the translation didn't go through instead, and
your key is fine.

**The bot left my group as soon as I added it.** Only administrators can add
it. Ask an admin to do it, or get admin rights first.

**It's asking for a password I don't have.** Passwords can't be recovered.
Create a new account with `/start` under a different username, then use
`/reauthenticate` in the group to link it with the new account.

**My files or images are ignored.** They're off until an admin turns them on
with `/filesettings`. If they are on, check the file type is allowed and the
file is under the size limit — the bot says which when it turns something down.

**"Daily translation limit's been hit."** The group has used its allowance for
the day. It resets at midnight, server time.

**The group's translating into the wrong language.** An admin can fix it with
`/setlanguage` in the group.

## Feedback

Found a bug, or want something the bot doesn't do? Send `/feedback` in a
private chat with the bot and write what's on your mind. It goes straight to
the people running it.

## License

Copyright (C) 2026 BlindSoldier52

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <https://www.gnu.org/licenses/>.

The full text is in [LICENSE](LICENSE).

---

Running your own copy of this bot? Setup, deployment and database details are
in [DEPLOYMENT.md](DEPLOYMENT.md).
