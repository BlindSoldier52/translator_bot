import logging

from sqlalchemy import select
from telegram import Update, User as TelegramUser
from telegram.error import Forbidden, TelegramError
from telegram.ext import ContextTypes

from bot.constants import (
	FLOW_GROUP_AUTH,
	FLOW_SET_LANGUAGE,
	MAX_AUTH_ATTEMPTS,
	STEP_LANGUAGE_CHOICE,
	STEP_PASSWORD,
	STEP_USERNAME,
)
from bot.handlers.common import (
	clear_flow,
	describe_languages,
	encode_chat_id_for_deep_link,
	get_chat_member_status,
	is_chat_admin,
)
from shared.db import session_scope
from shared.lockout import LoginGuard, describe_wait
from shared.models import Group, User
from shared.security import verify_password_async

logger = logging.getLogger(__name__)

account_guard = LoginGuard("bot-account")
requester_guard = LoginGuard("bot-requester", threshold=10)

LOCKED_ACCOUNT_MESSAGE = (
	"That account has had too many failed sign-ins, so it's locked for {wait}. "
	"Try again after that, or use /cancel."
)
LOCKED_REQUESTER_MESSAGE = (
	"You've had too many failed sign-ins, so I've paused authentication for {wait}. "
	"Try again after that."
)


async def begin_group_auth(context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, chat_id: int) -> str | None:
	try:
		chat = await context.bot.get_chat(chat_id)
	except TelegramError:
		return "I couldn't find that group anymore."

	if not await is_chat_admin(context.bot, chat_id, user.id):
		return "You are not currently an administrator of that group."

	locked = await requester_guard.remaining_lockout(str(user.id))
	if locked:
		return LOCKED_REQUESTER_MESSAGE.format(wait=describe_wait(locked))

	context.application.user_data[user.id]["flow"] = {
		"type": FLOW_GROUP_AUTH,
		"step": STEP_USERNAME,
		"chat_id": chat_id,
		"chat_title": chat.title,
		"attempts": 0,
	}
	await context.bot.send_message(
		user.id,
		f'To activate translations in "{chat.title}", please authenticate.\n\nPlease send your username.',
	)
	return None


async def handle_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	change = update.my_chat_member
	if change is None:
		return

	chat = change.chat
	if chat.type not in ("group", "supergroup"):
		return
	if change.new_chat_member.user.id != context.bot.id:
		return

	old_status = change.old_chat_member.status
	new_status = change.new_chat_member.status

	if old_status in ("left", "kicked") and new_status in ("member", "administrator"):
		await start_group_authentication(context, chat, change.from_user)
	elif new_status in ("left", "kicked"):
		async with session_scope() as session:
			group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat.id))
			if group is not None:
				group.is_active = False


async def start_group_authentication(context: ContextTypes.DEFAULT_TYPE, chat, adder: TelegramUser) -> None:
	if not await is_chat_admin(context.bot, chat.id, adder.id):
		try:
			await context.bot.send_message(
				adder.id,
				"Only group administrators can add me to a group. I'm leaving now.",
			)
		except TelegramError:
			logger.info("Could not DM non-admin adder %s for chat %s", adder.id, chat.id)
		try:
			await context.bot.leave_chat(chat.id)
		except TelegramError:
			logger.exception("Could not leave chat %s after non-admin add", chat.id)
		return

	try:
		error = await begin_group_auth(context, adder, chat.id)
		if error:
			await context.bot.send_message(adder.id, error)
	except Forbidden:
		bot_username = (await context.bot.get_me()).username
		payload = encode_chat_id_for_deep_link(chat.id)
		url = f"https://t.me/{bot_username}?start=auth_{payload}"
		await context.bot.send_message(
			chat.id,
			f"Hi {adder.mention_html()}! To authenticate me for this group, please start a private "
			f"chat with me first, at {url}, and I'll carry on from there.",
			parse_mode="HTML",
		)


async def handle_group_auth_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	chat_id = update.effective_chat.id

	if flow["step"] == STEP_USERNAME:
		flow["username"] = update.message.text.strip()
		flow["step"] = STEP_PASSWORD
		await update.message.reply_text("Now send your password.")
		return

	if flow["step"] != STEP_PASSWORD:
		return

	password = update.message.text
	try:
		await update.message.delete()
	except TelegramError:
		logger.debug("Could not delete password message in chat %s", chat_id)

	group_chat_id = flow["chat_id"]
	group_title = flow["chat_title"]
	username = flow.get("username", "")

	requester_id = str(update.effective_user.id)
	locked = await requester_guard.remaining_lockout(requester_id)
	if not locked:
		locked = await account_guard.remaining_lockout(username)
	if locked:
		clear_flow(context.user_data)
		await context.bot.send_message(
			chat_id, LOCKED_ACCOUNT_MESSAGE.format(wait=describe_wait(locked))
		)
		return

	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.username == username))
		stored_hash = account.password_hash if account is not None and not account.is_blocked else None
		password_ok = await verify_password_async(stored_hash, password)
		ok = account is not None and not account.is_blocked and password_ok
		owner_user_id = account.id if ok else None

	if ok:
		await account_guard.reset(username)
		await requester_guard.reset(requester_id)
		still_admin = await is_chat_admin(context.bot, group_chat_id, update.effective_user.id)
		if not still_admin:
			clear_flow(context.user_data)
			await context.bot.send_message(
				chat_id,
				"You are no longer an administrator of that group, so I can't activate translations there.",
			)
			return

		async with session_scope() as session:
			group = await session.scalar(select(Group).where(Group.telegram_chat_id == group_chat_id))
			if group is not None and group.is_blocked:
				clear_flow(context.user_data)
				await context.bot.send_message(
					chat_id,
					"This group has been blocked by the bot admins, so I can't activate translations there.",
				)
				return

			if group is None:
				group = Group(telegram_chat_id=group_chat_id, title=group_title, owner_user_id=owner_user_id)
				session.add(group)
			else:
				group.title = group_title
				group.owner_user_id = owner_user_id
				group.is_active = True

			owner = await session.get(User, owner_user_id) if owner_user_id else None
			owner_has_key = owner is not None and owner.api_key_provider is not None

		clear_flow(context.user_data)
		context.user_data["flow"] = {
			"type": FLOW_SET_LANGUAGE,
			"step": STEP_LANGUAGE_CHOICE,
			"chat_id": group_chat_id,
		}
		await context.bot.send_message(
			chat_id, f'Authentication successful! I am now active in "{group_title}".'
		)
		if not owner_has_key:
			await context.bot.send_message(
				chat_id,
				"Before I can translate anything there, I need an API key. Set one with "
				"/setapikey and I'll use it for the whole group, unless someone has their own.",
			)
		await context.bot.send_message(
			chat_id,
			f'Which language is mostly spoken in "{group_title}"? Send me the language name, '
			f"like Spanish. I can work with {describe_languages()}. Send auto instead and I'll "
			"work it out myself from the next 20 messages or so.",
		)
		return

	account_lock = await account_guard.register_failure(username)
	requester_lock = await requester_guard.register_failure(requester_id)
	logger.warning(
		"Failed group authentication for username %r by telegram user %s in chat %s",
		username,
		requester_id,
		group_chat_id,
	)

	flow["attempts"] += 1
	flow["step"] = STEP_USERNAME
	flow.pop("username", None)
	remaining = MAX_AUTH_ATTEMPTS - flow["attempts"]

	lock_seconds = max(account_lock, requester_lock)
	if lock_seconds:
		clear_flow(context.user_data)
		await context.bot.send_message(
			chat_id,
			"That username and password don't match, and there have been too many failed tries. "
			f"Authentication is locked for {describe_wait(lock_seconds)}.",
		)
		await leave_after_failure(context, group_chat_id)
		return

	if remaining <= 0:
		clear_flow(context.user_data)
		await context.bot.send_message(
			chat_id, "Authentication failed 3 times. For security, I'm leaving the group now."
		)
		await leave_after_failure(context, group_chat_id)
		return

	await context.bot.send_message(
		chat_id,
		f"That username/password combination is incorrect. You have {remaining} attempt(s) left. "
		"Please send your username again.",
	)


async def leave_after_failure(context: ContextTypes.DEFAULT_TYPE, group_chat_id: int) -> None:
	try:
		await context.bot.leave_chat(group_chat_id)
	except TelegramError:
		logger.exception("Could not leave chat %s after failed authentication", group_chat_id)


async def reauthenticate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	chat = update.effective_chat
	if chat is None or chat.type not in ("group", "supergroup"):
		return

	user = update.effective_user
	if not await is_chat_admin(context.bot, chat.id, user.id):
		await update.message.reply_text("Only group administrators can use this command.")
		return

	async with session_scope() as session:
		group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat.id))
		if group is not None and group.is_blocked:
			await update.message.reply_text(
				"This group has been blocked by the bot admins, so I can't be activated here."
			)
			return

	try:
		error = await begin_group_auth(context, user, chat.id)
	except Forbidden:
		bot_username = (await context.bot.get_me()).username
		payload = encode_chat_id_for_deep_link(chat.id)
		url = f"https://t.me/{bot_username}?start=auth_{payload}"
		await update.message.reply_text(
			f"Please start a private chat with me first, at {url}, and I'll carry on from there."
		)
		return

	if error:
		await update.message.reply_text(error)
		return

	await update.message.reply_text("I've sent you a private message to continue authentication.")


async def recheck_group_admins(context: ContextTypes.DEFAULT_TYPE) -> None:
	async with session_scope() as session:
		groups = (await session.scalars(select(Group).where(Group.is_active == True))).all()  # noqa: E712

		for group in groups:
			if group.owner_user_id is None:
				continue
			owner = await session.get(User, group.owner_user_id)
			if owner is None:
				continue

			if owner.is_blocked:
				group.is_active = False
				logger.info("Deactivated group %s because its owner is blocked", group.id)
				continue

			status = await get_chat_member_status(context.bot, group.telegram_chat_id, owner.telegram_user_id)
			if status is None:
				continue
			if status in ("administrator", "creator"):
				continue

			group.is_active = False
			try:
				await context.bot.send_message(
					owner.telegram_user_id,
					f'You are no longer an administrator of "{group.title}", so I have deactivated '
					"translations there. A current group administrator can run /reauthenticate in "
					"the group to reactivate them.",
				)
			except TelegramError:
				logger.info("Could not notify former admin %s about deactivation", owner.telegram_user_id)
