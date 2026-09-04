import logging

from telegram import BotCommand, Update
from telegram.ext import (
	Application,
	ChatMemberHandler,
	CommandHandler,
	MessageHandler,
	TypeHandler,
	filters,
)

from bot.constants import (
	ADMIN_RECHECK_INTERVAL_SECONDS,
	ANNOUNCEMENT_POLL_INTERVAL_SECONDS,
	LOGIN_ATTEMPT_PRUNE_INTERVAL_SECONDS,
	MAX_CONCURRENT_UPDATES,
)
from bot.handlers.announcements import send_pending_announcements
from bot.handlers.api_key import apikeystatus_command, removeapikey_command, setapikey_command
from bot.handlers.feedback import feedback_command
from bot.handlers.file_settings import filesettings_command
from bot.handlers.file_translate import handle_group_document, handle_private_document
from bot.handlers.gate import stop_blocked_users
from bot.handlers.image_translate import handle_group_image, handle_private_image
from bot.handlers.group_auth import handle_bot_added_to_group, reauthenticate_command, recheck_group_admins
from bot.handlers.language import setlanguage_command
from bot.handlers.privacy import privacy_command
from bot.handlers.registration import cancel_command, handle_private_text, help_command, start_command
from bot.handlers.translate import handle_group_message, translate_command
from shared.config import get_settings

logging.basicConfig(
	format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
	level=get_settings().log_level,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def warm_ocr_models(context) -> None:
	from sqlalchemy import select

	from shared.db import session_scope
	from shared.images.ocr import warm_models
	from shared.models import Group

	try:
		async with session_scope() as session:
			codes = (
				await session.scalars(select(Group.primary_language).where(Group.is_active.is_(True)))
			).all()
		await warm_models(list(codes))
		logger.info("OCR models warmed up")
	except Exception:
		logger.info("Could not warm up the OCR models", exc_info=True)


async def prune_login_attempts(context) -> None:
	from shared.lockout import forget_stale_attempts

	try:
		removed = await forget_stale_attempts()
	except Exception:
		logger.info("Could not prune the login attempt table", exc_info=True)
		return
	if removed:
		logger.info("Pruned %s stale login attempt rows", removed)


async def check_stored_keys() -> None:
	from sqlalchemy import select

	from shared.crypto import DecryptionError, decrypt_api_key
	from shared.db import session_scope
	from shared.models import User

	unreadable = 0
	async with session_scope() as session:
		rows = (
			await session.execute(
				select(User.id, User.api_key_encrypted).where(User.api_key_encrypted.is_not(None))
			)
		).all()

	for user_id, encrypted in rows:
		try:
			decrypt_api_key(user_id, encrypted)
		except DecryptionError:
			unreadable += 1

	if unreadable:
		logger.error(
			"%s of %s stored API keys could not be decrypted. The encryption secret has changed, "
			"so those users have to set their key again with /setapikey.",
			unreadable,
			len(rows),
		)
	else:
		logger.info("All %s stored API keys are readable", len(rows))


async def post_init(application: Application) -> None:
	try:
		await check_stored_keys()
	except Exception:
		logger.warning("Could not check the stored API keys at startup", exc_info=True)

	await application.bot.set_my_commands(
		[
			BotCommand("start", "Create your account or see a welcome message"),
			BotCommand("help", "Show available commands"),
			BotCommand("cancel", "Cancel whatever you're currently doing"),
			BotCommand("feedback", "Send feedback to the admins"),
			BotCommand("privacy", "See what I do with your data"),
			BotCommand("setapikey", "Give me the API key I translate with"),
			BotCommand("removeapikey", "Remove your API key"),
			BotCommand("apikeystatus", "Show which key your translations use"),
			BotCommand("setlanguage", "Change the group's main language, e.g. /setlanguage spanish"),
			BotCommand("reauthenticate", "Re-link this group to your account (group admins only)"),
			BotCommand("translate", "Translate text to a language, e.g. /translate spanish hello"),
			BotCommand("filesettings", "Set up file and image translation for your group or this chat"),
		]
	)


def build_application() -> Application:
	settings = get_settings()
	application = (
		Application.builder()
		.token(settings.telegram_bot_token)
		.concurrent_updates(MAX_CONCURRENT_UPDATES)
		.post_init(post_init)
		.build()
	)

	application.add_handler(TypeHandler(Update, stop_blocked_users), group=-1)

	application.add_handler(CommandHandler("start", start_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("help", help_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("cancel", cancel_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("feedback", feedback_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("privacy", privacy_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("setapikey", setapikey_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("removeapikey", removeapikey_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("apikeystatus", apikeystatus_command, filters.ChatType.PRIVATE))
	application.add_handler(CommandHandler("filesettings", filesettings_command, filters.ChatType.PRIVATE))
	application.add_handler(
		MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_private_text)
	)
	application.add_handler(
		MessageHandler(
			filters.ChatType.PRIVATE & (filters.PHOTO | filters.Document.IMAGE), handle_private_image
		)
	)
	application.add_handler(
		MessageHandler(filters.ChatType.PRIVATE & filters.Document.ALL, handle_private_document)
	)

	application.add_handler(ChatMemberHandler(handle_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))
	application.add_handler(
		CommandHandler("reauthenticate", reauthenticate_command, filters.ChatType.GROUPS)
	)
	application.add_handler(
		CommandHandler("setlanguage", setlanguage_command, filters.ChatType.GROUPS)
	)
	application.add_handler(CommandHandler("translate", translate_command, filters.ChatType.GROUPS))

	application.add_handler(
		MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, handle_group_message)
	)
	application.add_handler(
		MessageHandler(
			filters.ChatType.GROUPS & (filters.PHOTO | filters.Document.IMAGE), handle_group_image
		)
	)
	application.add_handler(
		MessageHandler(filters.ChatType.GROUPS & filters.Document.ALL, handle_group_document)
	)

	if application.job_queue is not None:
		application.job_queue.run_repeating(
			recheck_group_admins, interval=ADMIN_RECHECK_INTERVAL_SECONDS, first=ADMIN_RECHECK_INTERVAL_SECONDS
		)
		application.job_queue.run_repeating(
			send_pending_announcements, interval=ANNOUNCEMENT_POLL_INTERVAL_SECONDS, first=10
		)
		application.job_queue.run_repeating(
			prune_login_attempts,
			interval=LOGIN_ATTEMPT_PRUNE_INTERVAL_SECONDS,
			first=LOGIN_ATTEMPT_PRUNE_INTERVAL_SECONDS,
		)
		application.job_queue.run_once(warm_ocr_models, when=5)

	return application


def main() -> None:
	application = build_application()
	logger.info("Starting bot with long polling")
	application.run_polling(allowed_updates=["message", "my_chat_member"])


if __name__ == "__main__":
	main()
