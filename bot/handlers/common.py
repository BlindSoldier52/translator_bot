import logging

from telegram import Bot
from telegram.error import TelegramError

from bot.constants import AUTO_DETECT_CODE, TELEGRAM_MESSAGE_LIMIT
from shared.providers import PROVIDERS
from shared.translation import COMMON_LANGUAGES

logger = logging.getLogger(__name__)


def split_for_telegram(text: str) -> list[str]:
	chunks: list[str] = []
	remaining = text
	while len(remaining) > TELEGRAM_MESSAGE_LIMIT:
		cut = remaining.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT)
		if cut <= 0:
			cut = remaining.rfind(" ", 0, TELEGRAM_MESSAGE_LIMIT)
		if cut <= 0:
			cut = TELEGRAM_MESSAGE_LIMIT
		chunks.append(remaining[:cut].strip())
		remaining = remaining[cut:].strip()
	if remaining:
		chunks.append(remaining)
	return chunks


async def reply_in_chunks(message, text: str) -> bool:
	"""Send a reply that may be longer than one Telegram message. False if any part failed."""
	if not text.strip():
		logger.info("Refusing to send an empty reply to chat %s", message.chat_id)
		return False
	for chunk in split_for_telegram(text):
		try:
			await message.reply_text(chunk)
		except TelegramError:
			logger.exception("Could not send a reply to chat %s", message.chat_id)
			return False
	return True


async def get_chat_member_status(bot: Bot, chat_id: int, user_id: int) -> str | None:
	try:
		member = await bot.get_chat_member(chat_id, user_id)
	except TelegramError:
		logger.warning("Could not fetch chat member %s in chat %s", user_id, chat_id)
		return None
	return member.status


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
	status = await get_chat_member_status(bot, chat_id, user_id)
	return status in ("administrator", "creator")


def join_words(items: list[str], conjunction: str = "and") -> str:
	if not items:
		return ""
	if len(items) == 1:
		return items[0]
	return f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


def describe_languages() -> str:
	return join_words(list(COMMON_LANGUAGES.values()))


def describe_providers() -> str:
	return join_words([provider.code for provider in PROVIDERS.values()], conjunction="or")


def resolve_language(text: str) -> str | None:
	cleaned = " ".join(text.split()).lower()
	if cleaned in ("auto", "automatic", "automatically", "detect"):
		return AUTO_DETECT_CODE
	if cleaned in COMMON_LANGUAGES:
		return cleaned
	for code, name in COMMON_LANGUAGES.items():
		if name.lower() == cleaned:
			return code
	return None


def resolve_provider(text: str):
	cleaned = " ".join(text.split()).lower()
	for provider in PROVIDERS.values():
		if cleaned in (provider.code, provider.label.lower()):
			return provider
	for provider in PROVIDERS.values():
		if cleaned and provider.label.lower().startswith(cleaned):
			return provider
	return None


def encode_chat_id_for_deep_link(chat_id: int) -> str:
	if chat_id < 0:
		return f"n{-chat_id}"
	return str(chat_id)


def decode_chat_id_from_deep_link(payload: str) -> int | None:
	try:
		if payload.startswith("n"):
			return -int(payload[1:])
		return int(payload)
	except ValueError:
		return None


def clear_flow(user_data: dict) -> None:
	user_data.pop("flow", None)
