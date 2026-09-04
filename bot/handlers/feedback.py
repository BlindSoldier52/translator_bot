import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.constants import FEEDBACK_MAX_LEN, FLOW_FEEDBACK, STEP_FEEDBACK_MESSAGE
from bot.handlers.common import clear_flow
from shared.db import session_scope
from shared.models import Feedback, User

logger = logging.getLogger(__name__)


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		existing = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))

	if existing is None:
		await update.message.reply_text(
			"You need an account first. Use /start to create one, then try /feedback again."
		)
		return

	clear_flow(context.user_data)
	context.user_data["flow"] = {"type": FLOW_FEEDBACK, "step": STEP_FEEDBACK_MESSAGE}
	await update.message.reply_text(
		"Please send your feedback as a single message (it can span multiple lines). Use /cancel to stop."
	)


async def handle_feedback_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	text = update.message.text.strip()
	if not text:
		await update.message.reply_text("Feedback can't be empty. Please try again, or /cancel.")
		return
	if len(text) > FEEDBACK_MAX_LEN:
		await update.message.reply_text(
			f"That's too long ({len(text)} characters, max {FEEDBACK_MAX_LEN}). Please shorten it and resend."
		)
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		if account is None:
			clear_flow(context.user_data)
			await update.message.reply_text("Your account could not be found. Please /start again.")
			return
		session.add(Feedback(user_id=account.id, message=text))

	clear_flow(context.user_data)
	await update.message.reply_text("Thanks! Your feedback has been recorded.")
