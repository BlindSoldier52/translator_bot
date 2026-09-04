from telegram import Update
from telegram.ext import ContextTypes

PRIVACY_TEXT = (
	"Here's what I do with your data.\n\n"
	"Your password is hashed with argon2 the moment you send it, and the message you typed it "
	"in is deleted from our chat straight away. Nobody can read it back, not even the people "
	"running me, which also means it can't be recovered if you forget it.\n\n"
	"Your API key is encrypted before it's stored, with a key derived separately for your "
	"account, and the message you pasted it in is deleted right away too. It's only ever "
	"decrypted to send a translation request to the provider you chose.\n\n"
	"I don't keep the messages I translate. Once I've sent a translation back, all I record is "
	"that a translation happened, which languages it went between, and which group it was in. "
	"The text itself, your name and your Telegram id are not stored anywhere.\n\n"
	"Files and images are handled entirely in memory. Nothing is written to disk, not the file "
	"you sent, not the translated file or image I build, and everything is dropped as soon as "
	"I've replied.\n\n"
	"One thing worth being clear about: to translate anything, the text has to be sent to the "
	"AI provider whose key is being used, which is Anthropic, OpenAI, OpenRouter, xAI, DeepSeek "
	"or GLM. What they do with it is covered by their own terms, not mine. If that matters to "
	"you, pick the provider you trust.\n\n"
	"If you send feedback with /feedback, that message is stored and read by the people running "
	"me, so leave anything private out of it. Group admins can see and change the settings of "
	"their own groups, never the content of anyone's messages."
)


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return
	await update.message.reply_text(PRIVACY_TEXT)
