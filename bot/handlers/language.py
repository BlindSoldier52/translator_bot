import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.constants import AUTO_DETECT_CODE
from bot.handlers.common import clear_flow, describe_languages, is_chat_admin, resolve_language
from shared.db import session_scope
from shared.models import Group
from shared.translation import COMMON_LANGUAGES

logger = logging.getLogger(__name__)

UNKNOWN_LANGUAGE_MESSAGE = (
	"I don't know that one. I can work with {languages}. Send auto instead and I'll work it "
	"out myself from the next 20 messages or so."
)


async def setlanguage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	chat = update.effective_chat
	if chat is None or chat.type not in ("group", "supergroup"):
		await update.message.reply_text("This command can only be used inside a group.")
		return

	user = update.effective_user
	if not await is_chat_admin(context.bot, chat.id, user.id):
		await update.message.reply_text("Only group administrators can change the group's language.")
		return

	async with session_scope() as session:
		group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat.id))
		known = group is not None and group.is_active and not group.is_blocked

	if not known:
		await update.message.reply_text(
			"I'm not active in this group yet. An administrator needs to authenticate me first "
			"with /reauthenticate."
		)
		return

	args = context.args or []
	if not args:
		await update.message.reply_text(
			"Send the language along with the command, like /setlanguage spanish. I can work "
			f"with {describe_languages()}. Send /setlanguage auto and I'll work it out myself "
			"from the next 20 messages or so."
		)
		return

	code = resolve_language(" ".join(args))
	if code is None:
		await update.message.reply_text(UNKNOWN_LANGUAGE_MESSAGE.format(languages=describe_languages()))
		return

	confirmation = await apply_language(chat.id, code)
	await update.message.reply_text(confirmation or "I couldn't find that group in my database.")


async def apply_language(chat_id: int, code: str) -> str | None:
	async with session_scope() as session:
		group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat_id))
		if group is None:
			return None

		group.language_votes = {}
		group.language_sample_count = 0

		if code == AUTO_DETECT_CODE:
			group.primary_language = None
			group.language_mode = "auto"
			return (
				"I'll work out the group's main language myself from the next 20 messages or so, "
				"then set it and let you know."
			)

		group.primary_language = code
		group.language_mode = "manual"
		return f'The main language for "{group.title}" is now {COMMON_LANGUAGES.get(code, code)}.'


async def handle_language_choice_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	code = resolve_language(update.message.text or "")
	if code is None:
		await update.message.reply_text(
			UNKNOWN_LANGUAGE_MESSAGE.format(languages=describe_languages()) + " Or /cancel to stop."
		)
		return

	confirmation = await apply_language(flow["chat_id"], code)
	clear_flow(context.user_data)
	await update.message.reply_text(confirmation or "I couldn't find that group in my database anymore.")
