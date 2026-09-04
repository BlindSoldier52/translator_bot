import datetime
import logging

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.constants import FLOW_SET_API_KEY, STEP_API_KEY_PROVIDER, STEP_API_KEY_VALUE
from bot.handlers.common import clear_flow, describe_providers, resolve_provider
from shared.crypto import encrypt_api_key
from shared.db import session_scope
from shared.models import User
from shared.providers import ProviderAuthError, ProviderError, get_provider

logger = logging.getLogger(__name__)


async def setapikey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
	if user is None:
		await update.message.reply_text(
			"You need an account first. Use /start to create one, then try /setapikey again."
		)
		return

	clear_flow(context.user_data)
	context.user_data["flow"] = {"type": FLOW_SET_API_KEY, "step": STEP_API_KEY_PROVIDER}
	await update.message.reply_text(
		f"Which provider's key do you want to use? Send me {describe_providers()}. "
		"Use /cancel to stop."
	)


async def handle_set_api_key_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	chat_id = update.effective_chat.id

	if flow["step"] == STEP_API_KEY_PROVIDER:
		provider = resolve_provider(update.message.text or "")
		if provider is None:
			await update.message.reply_text(
				f"I don't work with that one. Send me {describe_providers()}, or /cancel to stop."
			)
			return
		flow["provider"] = provider.code
		flow["step"] = STEP_API_KEY_VALUE
		await update.message.reply_text(
			f"Alright, paste your API key for {provider.label} here. This only works in this "
			"private chat, never share it in a group."
		)
		return

	provider = get_provider(flow.get("provider"))

	api_key = update.message.text.strip()
	try:
		await update.message.delete()
	except Exception:
		logger.debug("Could not delete API key message in chat %s", chat_id)

	if provider is None:
		clear_flow(context.user_data)
		await context.bot.send_message(chat_id, "Something went wrong, please start over with /setapikey.")
		return

	try:
		await provider.test_key(api_key)
	except ProviderAuthError:
		await context.bot.send_message(
			chat_id,
			"That key didn't work. Double check it's correct and has credit available, "
			"then try again with /setapikey.",
		)
		return
	except ProviderError:
		await context.bot.send_message(
			chat_id,
			f"I couldn't reach {provider.label} to check that key, so I haven't saved it. "
			"Try again with /setapikey in a moment.",
		)
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		if user is None:
			clear_flow(context.user_data)
			await context.bot.send_message(chat_id, "I couldn't find your account. Use /start first.")
			return
		user.api_key_provider = provider.code
		user.api_key_encrypted = encrypt_api_key(user.id, api_key)
		user.api_key_updated_at = datetime.datetime.now(datetime.timezone.utc)

	clear_flow(context.user_data)
	await context.bot.send_message(
		chat_id,
		f"You're all set. I'll use your {provider.label} key for your translations, and for "
		"everyone else's in any group you set me up in.",
	)


async def removeapikey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		if user is None or user.api_key_provider is None:
			await update.message.reply_text(
				"You don't have a key set, so there's nothing to remove."
			)
			return
		user.api_key_provider = None
		user.api_key_encrypted = None
		user.api_key_updated_at = None

	await update.message.reply_text(
		"Your key has been removed. I won't be able to translate for you until you set another "
		"one with /setapikey. In a group I'll fall back to the admin's key, if they have one, "
		"and if you're that admin your group has just gone quiet."
	)


async def apikeystatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		user = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))

	if user is None or user.api_key_provider is None:
		await update.message.reply_text(
			"You don't have a key set. In a group I'll use the admin's key if they have one, but "
			"in here I can't translate for you at all. Set one with /setapikey."
		)
		return

	provider = get_provider(user.api_key_provider)
	label = provider.label if provider else user.api_key_provider
	await update.message.reply_text(
		f"You're using your own {label} key. It pays for your own translations, and for everyone "
		"else's in any group you set me up in."
	)
