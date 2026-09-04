import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from telegram import Update
from telegram.ext import ContextTypes

from bot.constants import (
	FLOW_FEEDBACK,
	FLOW_FILE_SETTINGS,
	FLOW_FILE_TRANSLATE_LANGUAGE,
	FLOW_IMAGE_TRANSLATE_LANGUAGE,
	FLOW_GROUP_AUTH,
	FLOW_REGISTER,
	FLOW_SET_API_KEY,
	FLOW_SET_LANGUAGE,
	STEP_PASSWORD,
	STEP_USERNAME,
)
from bot.handlers.api_key import handle_set_api_key_step
from bot.handlers.common import clear_flow, decode_chat_id_from_deep_link
from bot.handlers.feedback import handle_feedback_step
from bot.handlers.file_settings import handle_file_settings_step
from bot.handlers.file_translate import handle_file_language_step
from bot.handlers.group_auth import begin_group_auth, handle_group_auth_step
from bot.handlers.image_translate import handle_image_language_step
from bot.handlers.language import handle_language_choice_step
from shared.db import session_scope
from shared.models import Announcement, AnnouncementDelivery, User
from shared.security import (
	PASSWORD_MIN_LEN,
	USERNAME_MAX_LEN,
	USERNAME_MIN_LEN,
	hash_password_async,
	validate_password,
	validate_username,
)

logger = logging.getLogger(__name__)

HELP_TEXT = (
	"Here's what I can do.\n\n"
	"In a private chat with me, /start creates your account, /help shows this message, and "
	"/cancel stops whatever we're in the middle of. /feedback sends a note to the bot admins, "
	"and /source tells you where to get the code I run on.\n\n"
	"/setapikey gives me the API key I translate with. I need one to work at all, so this is "
	"the first thing to do. In a group I use the sender's key if they have one, otherwise the "
	"key of the admin who set me up there. /removeapikey takes yours away again, and "
	"/apikeystatus tells you where you stand.\n\n"
	"/filesettings sets up file and image translation, either for a group you administer or "
	"for this chat. Once it's on, send me a file or a photo here and I'll translate it. I can "
	"read .txt, .pdf, .docx and .srt files, and I can read text out of images in just about "
	"any script.\n\n"
	"In a group where I'm active, administrators can use /setlanguage to change the group's "
	"main language, like /setlanguage spanish or /setlanguage auto, or /reauthenticate to "
	"re-link the group to their account if I deactivated myself there.\n\n"
	"Anyone in that group can use /translate, like /translate spanish hello there. You can "
	"also reply to a message with /translate spanish to translate just that message.\n\n"
	"To add me to a group, add me as a member and then message me to authenticate. Only group "
	"administrators can do this."
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	telegram_user = update.effective_user
	args = context.args or []

	if args and args[0].startswith("auth_"):
		chat_id = decode_chat_id_from_deep_link(args[0][len("auth_"):])
		if chat_id is not None:
			await resume_group_auth_via_deep_link(update, context, chat_id)
			return

	async with session_scope() as session:
		existing = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))

	if existing:
		await update.message.reply_text("Welcome back! You already have an account. Use /help to see what I can do.")
		return

	clear_flow(context.user_data)
	context.user_data["flow"] = {"type": FLOW_REGISTER, "step": STEP_USERNAME}
	await update.message.reply_text(
		"Welcome! Let's create your account.\n\n"
		f"Please choose a username ({USERNAME_MIN_LEN}-{USERNAME_MAX_LEN} characters, no spaces)."
	)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text(HELP_TEXT)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return
	clear_flow(context.user_data)
	await update.message.reply_text("Cancelled. Use /help to see available commands.")


async def resume_group_auth_via_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
	telegram_user = update.effective_user

	async with session_scope() as session:
		existing = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))

	if existing is None:
		clear_flow(context.user_data)
		context.user_data["flow"] = {
			"type": FLOW_REGISTER,
			"step": STEP_USERNAME,
			"then_auth_chat_id": chat_id,
		}
		await update.message.reply_text(
			"You don't have an account yet. Let's create one first.\n\n"
			f"Please choose a username ({USERNAME_MIN_LEN}-{USERNAME_MAX_LEN} characters, no spaces)."
		)
		return

	error = await begin_group_auth(context, telegram_user, chat_id)
	if error:
		await update.message.reply_text(error)


async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	flow = context.user_data.get("flow")
	if not flow:
		await update.message.reply_text("I didn't understand that. Use /help to see available commands.")
		return

	if flow["type"] == FLOW_REGISTER:
		await handle_register_step(update, context, flow)
	elif flow["type"] == FLOW_GROUP_AUTH:
		await handle_group_auth_step(update, context, flow)
	elif flow["type"] == FLOW_FEEDBACK:
		await handle_feedback_step(update, context, flow)
	elif flow["type"] == FLOW_SET_API_KEY:
		await handle_set_api_key_step(update, context, flow)
	elif flow["type"] == FLOW_FILE_SETTINGS:
		await handle_file_settings_step(update, context, flow)
	elif flow["type"] == FLOW_FILE_TRANSLATE_LANGUAGE:
		await handle_file_language_step(update, context, flow)
	elif flow["type"] == FLOW_SET_LANGUAGE:
		await handle_language_choice_step(update, context, flow)
	elif flow["type"] == FLOW_IMAGE_TRANSLATE_LANGUAGE:
		await handle_image_language_step(update, context, flow)


async def handle_register_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	chat_id = update.effective_chat.id

	if flow["step"] == STEP_USERNAME:
		username = update.message.text.strip()
		error = validate_username(username)
		if error:
			await update.message.reply_text(f"{error} Please try again.")
			return

		async with session_scope() as session:
			taken = await session.scalar(select(User).where(User.username == username))
		if taken:
			await update.message.reply_text("This username is already taken. Please choose another one.")
			return

		flow["username"] = username
		flow["step"] = STEP_PASSWORD
		await update.message.reply_text(
			f"Great. Now choose a password (at least {PASSWORD_MIN_LEN} characters, no spaces).\n"
			"For your privacy, I will delete your message from this chat right after you send it."
		)
		return

	if flow["step"] == STEP_PASSWORD:
		password = update.message.text
		try:
			await update.message.delete()
		except Exception:
			logger.debug("Could not delete password message in chat %s", chat_id)

		error = validate_password(password)
		if error:
			await context.bot.send_message(chat_id, f"{error} Please choose another password.")
			return

		username = flow.get("username", "")
		telegram_user = update.effective_user
		password_hash = await hash_password_async(password)

		try:
			async with session_scope() as session:
				user = User(
					telegram_user_id=telegram_user.id,
					username=username,
					password_hash=password_hash,
				)
				session.add(user)
				await session.flush()

				latest_announcement = await session.scalar(
					select(Announcement).order_by(Announcement.created_at.desc()).limit(1)
				)
				if latest_announcement is not None:
					session.add(
						AnnouncementDelivery(announcement_id=latest_announcement.id, user_id=user.id)
					)
		except IntegrityError:
			clear_flow(context.user_data)
			await context.bot.send_message(
				chat_id,
				"I couldn't create that account (username or account may already exist). Please /start again.",
			)
			return

		then_auth_chat_id = flow.get("then_auth_chat_id")
		clear_flow(context.user_data)
		await context.bot.send_message(
			chat_id,
			"Your account has been created successfully! One more thing before I can translate "
			"anything: give me an API key with /setapikey.",
		)

		if then_auth_chat_id is not None:
			error = await begin_group_auth(context, telegram_user, then_auth_chat_id)
			if error:
				await context.bot.send_message(chat_id, error)
