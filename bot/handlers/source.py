from telegram import Update
from telegram.ext import ContextTypes

from shared.config import get_settings

SOURCE_TEXT = (
	"I'm free software under the AGPL-3.0, which means you're entitled to read the exact "
	"source I'm running, and to run your own copy. You'll find it at {url}\n\n"
	"Whoever runs this particular copy decides where it's hosted and what they do with the "
	"data it handles, so ask them if you want to know more than the source tells you."
)


async def source_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None:
		return
	await update.effective_message.reply_text(
		SOURCE_TEXT.format(url=get_settings().source_url)
	)
