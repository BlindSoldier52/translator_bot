import logging

from sqlalchemy import select
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from shared.db import session_scope
from shared.models import User

logger = logging.getLogger(__name__)

BLOCKED_MESSAGE = (
	"Your account has been blocked by the bot admins, so I can't translate anything or change "
	"any settings for you. If you think that's a mistake, the people running the bot are the "
	"ones to talk to."
)


async def stop_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Runs before every other handler and drops updates from blocked accounts."""
	telegram_user = update.effective_user
	if telegram_user is None:
		return

	async with session_scope() as session:
		blocked = await session.scalar(
			select(User.is_blocked).where(User.telegram_user_id == telegram_user.id)
		)

	if not blocked:
		return

	chat = update.effective_chat
	message = update.effective_message
	if message is not None and chat is not None and chat.type == "private":
		if not context.user_data.get("blocked_notice"):
			context.user_data["blocked_notice"] = True
			try:
				await message.reply_text(BLOCKED_MESSAGE)
			except TelegramError:
				logger.info("Could not tell blocked user %s about the block", telegram_user.id)

	logger.info("Dropped an update from blocked user %s", telegram_user.id)
	raise ApplicationHandlerStop
