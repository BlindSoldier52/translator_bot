import logging
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.constants import (
	DEFAULT_MAINTENANCE_MESSAGE,
	DETECTION_CONFIDENCE_SKIP_THRESHOLD,
	LANGUAGE_AUTO_DETECT_SAMPLE_THRESHOLD,
)
from bot.handlers.common import reply_in_chunks
from shared.config import get_settings
from shared.crypto import DecryptionError, decrypt_api_key
from shared.db import session_scope
from shared.languages import UnknownLanguageError, language_name, resolve_language_code
from shared.models import (
	AppSettings,
	DailyCounter,
	Group,
	GroupDailyCounter,
	GroupMaintenanceNotice,
	GroupWarning,
	Translation,
	User,
)
from shared.providers import get_provider
from shared.translation import (
	PersonalKeyError,
	ProviderUnavailableError,
	detect_language,
	detect_translation_request,
	explain_term,
	translate_text,
)

logger = logging.getLogger(__name__)

TRANSLATION_REQUEST_HINT_RE = re.compile(
	r"\btranslate\b"
	r"|\bhow (?:do you|to) say\b"
	r"|\b(?:in|into|to)\s+[a-zA-Z]{3,}[\s.?!]*$"
	r"|\bformal(?:ly)?\b"
	r"|\binformal(?:ly)?\b"
	r"|\bcasual(?:ly)?\b"
	r"|\bslang\b",
	re.IGNORECASE,
)

MISSING_KEY_GROUP_MESSAGE = (
	"I can't translate here until someone gives me an API key. The admin who set me up can "
	"add one with /setapikey in a private chat with me, and I'll use it for the whole group. "
	"You can also add your own and I'll use that for your messages."
)
MISSING_KEY_PRIVATE_MESSAGE = (
	"You need your own API key for that. Set one with /setapikey and try again."
)
UNKNOWN_LANGUAGE_MESSAGE = (
	"I don't know that language, so I left the message alone. Try a language name like "
	"Spanish, Japanese or Urdu."
)
TRANSLATION_FAILED_MESSAGE = (
	"That translation didn't go through, sorry. Try again in a moment."
)

MAX_INTENT_PARSE_CHARS = 1000


@dataclass(frozen=True)
class TranslationKey:
	provider_code: str
	api_key: str
	owner_telegram_id: int
	owner_is_sender: bool


async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	chat = update.effective_chat
	if message is None or chat is None or chat.type not in ("group", "supergroup"):
		return
	if not message.text:
		return

	async with session_scope() as session:
		group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat.id))
		if group is None or not group.is_active or group.is_blocked:
			return
		group_id = group.id
		group_title = group.title
		primary_language = group.primary_language
		group_limit = group.daily_message_limit

	if await maybe_handle_maintenance(context, group_id, chat.id):
		return

	if primary_language is None:
		detection = await detect_language(message.text)
		if detection is None or detection.confidence < DETECTION_CONFIDENCE_SKIP_THRESHOLD:
			return
		settled = None
		async with session_scope() as session:
			group = await session.get(Group, group_id, with_for_update=True)
			if group is not None:
				settled = await collect_language_sample(session, group, detection.lang_code)
		if settled is not None:
			await announce_detected_language(context, settled[0], group_title, settled[1])
		return

	target_lang = primary_language
	sender_id = message.from_user.id if message.from_user else None

	key = await resolve_translation_key(sender_id, group_id)
	if key is None:
		await warn_missing_key(context, message)
		return

	if (
		len(message.text) <= MAX_INTENT_PARSE_CHARS
		and TRANSLATION_REQUEST_HINT_RE.search(message.text)
		and await quota_is_available()
	):
		handled = await handle_translation_request(
			context, message, key, chat.id, group_id, group_title, group_limit
		)
		if handled:
			return

	detection = await detect_language(message.text, key.provider_code, key.api_key)
	if detection is None or detection.confidence < DETECTION_CONFIDENCE_SKIP_THRESHOLD:
		return
	if detection.lang_code == target_lang:
		return

	translated = await translate_for_message(
		context, key, group_id, group_limit, group_title, chat.id, message.text, target_lang
	)
	if translated is None:
		return

	if not await reply_in_chunks(message, translated):
		return

	async with session_scope() as session:
		session.add(
			Translation(
				group_id=group_id,
				source_lang=detection.lang_code,
				target_lang=target_lang,
			)
		)


async def handle_translation_request(
	context: ContextTypes.DEFAULT_TYPE,
	message,
	key: TranslationKey,
	chat_id: int,
	group_id: int,
	group_title: str,
	group_limit: int | None,
) -> bool:
	try:
		request = await detect_translation_request(key.provider_code, key.api_key, message.text)
	except ProviderUnavailableError:
		logger.info("Intent parsing was unavailable for chat %s", chat_id)
		return False
	except PersonalKeyError:
		await notify_key_failure(context, key, group_title)
		return True
	if request is None:
		return False

	last = context.chat_data.get("last_translation") if request.needs_context else None

	text_to_translate = request.text
	if not text_to_translate:
		if last is not None:
			text_to_translate = last["text"]
		elif message.reply_to_message and message.reply_to_message.text:
			text_to_translate = message.reply_to_message.text
		else:
			return False

	target_lang = request.language
	if not target_lang:
		if last is not None:
			target_lang = last["lang"]
		else:
			return False

	translated = await translate_for_message(
		context, key, group_id, group_limit, group_title, chat_id, text_to_translate, target_lang,
		style=request.style,
	)
	if translated is None:
		return True

	reply_parts = [translated]
	if request.explain:
		try:
			reply_parts.append(await explain_term(key.provider_code, key.api_key, text_to_translate))
		except PersonalKeyError:
			logger.info("Explanation failed for chat %s", chat_id)

	if not await reply_in_chunks(message, "\n\n".join(reply_parts)):
		return True

	context.chat_data["last_translation"] = {"text": text_to_translate, "lang": target_lang}
	return True


async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	chat = update.effective_chat
	if message is None or chat is None:
		return

	args = context.args or []
	if not args:
		await message.reply_text(
			"Usage: /translate <language> <text>, or reply to a message with /translate <language>."
		)
		return

	target_lang = resolve_language_code(args[0])
	if target_lang is None:
		await message.reply_text(
			"I don't know that language. Ask for one by name, like /translate spanish hello there."
		)
		return

	text_to_translate = " ".join(args[1:]).strip()
	if not text_to_translate:
		if message.reply_to_message and message.reply_to_message.text:
			text_to_translate = message.reply_to_message.text
		else:
			await message.reply_text(
				"Please provide text to translate, or reply to a message with /translate <language>."
			)
			return

	async with session_scope() as session:
		group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat.id))
		if group is None or not group.is_active or group.is_blocked:
			await message.reply_text("I'm not active in this group.")
			return
		group_id = group.id
		group_title = group.title
		group_limit = group.daily_message_limit

	if await maybe_handle_maintenance(context, group_id, chat.id):
		return

	sender_id = message.from_user.id if message.from_user else None
	key = await resolve_translation_key(sender_id, group_id)
	if key is None:
		await warn_missing_key(context, message)
		return

	translated = await translate_for_message(
		context, key, group_id, group_limit, group_title, chat.id, text_to_translate, target_lang
	)
	if translated is None:
		return

	await reply_in_chunks(message, translated)


async def collect_language_sample(session, group: Group, lang_code: str) -> tuple[int, str] | None:
	"""Tally one language vote. The caller must hold a row lock on the group.

	Returns the owner's Telegram id and the winning language once one is settled, so the
	caller can announce it after the transaction closes instead of holding the lock across
	a Telegram call.
	"""
	votes = dict(group.language_votes or {})
	votes[lang_code] = votes.get(lang_code, 0) + 1
	group.language_votes = votes
	group.language_sample_count += 1

	if group.language_sample_count < LANGUAGE_AUTO_DETECT_SAMPLE_THRESHOLD:
		return None

	winner = max(votes.items(), key=lambda item: item[1])[0]
	group.primary_language = winner
	group.language_votes = {}

	if group.owner_user_id is None:
		return None

	owner = await session.get(User, group.owner_user_id)
	if owner is None:
		return None
	return owner.telegram_user_id, winner


async def announce_detected_language(
	context: ContextTypes.DEFAULT_TYPE, owner_telegram_id: int, group_title: str, winner: str
) -> None:
	try:
		await context.bot.send_message(
			owner_telegram_id,
			f'I detected the main language of "{group_title}": {language_name(winner) or winner}. '
			"Translations are now active.",
		)
	except TelegramError:
		logger.info("Could not notify owner about the detected language for %r", group_title)


async def global_daily_limit(session) -> int:
	settings_row = await session.get(AppSettings, 1)
	return settings_row.daily_message_limit if settings_row else get_settings().default_daily_message_limit


async def take_from_counter(session, model, filters, insert_values, limit: int | None, units: int) -> bool:
	await session.execute(pg_insert(model).values(**insert_values).on_conflict_do_nothing())
	statement = update(model).where(*filters)
	if limit is not None:
		statement = statement.where(model.translated_count + units <= limit)
	result = await session.execute(
		statement.values(translated_count=model.translated_count + units)
	)
	return result.rowcount > 0


async def give_back_to_counter(session, model, filters, units: int) -> None:
	await session.execute(
		update(model)
		.where(*filters)
		.values(translated_count=func.greatest(model.translated_count - units, 0))
	)


@dataclass(frozen=True)
class QuotaTarget:
	"""Where a translation is charged: always the global counter, plus a per-group one."""

	group_id: int | None = None
	group_limit: int | None = None
	counter_model: type = GroupDailyCounter
	always_count_group: bool = False

	def counts_group(self) -> bool:
		if self.group_id is None:
			return False
		return self.always_count_group or self.group_limit is not None

	def group_filters(self, today: date):
		return (
			self.counter_model.group_id == self.group_id,
			self.counter_model.date == today,
		)

	async def take(self, units: int = 1) -> bool:
		if units <= 0:
			return True
		today = date.today()
		async with session_scope() as session:
			limit = await global_daily_limit(session)
			taken = await take_from_counter(
				session,
				DailyCounter,
				(DailyCounter.date == today,),
				{"date": today, "translated_count": 0},
				limit,
				units,
			)
			if not taken:
				await session.rollback()
				return False

			if not self.counts_group():
				return True

			taken = await take_from_counter(
				session,
				self.counter_model,
				self.group_filters(today),
				{"group_id": self.group_id, "date": today, "translated_count": 0},
				self.group_limit,
				units,
			)
			if not taken:
				await session.rollback()
				return False
			return True

	async def give_back(self, units: int = 1) -> None:
		if units <= 0:
			return
		today = date.today()
		async with session_scope() as session:
			await give_back_to_counter(session, DailyCounter, (DailyCounter.date == today,), units)
			if self.counts_group():
				await give_back_to_counter(session, self.counter_model, self.group_filters(today), units)


async def quota_is_available() -> bool:
	today = date.today()
	async with session_scope() as session:
		limit = await global_daily_limit(session)
		counter = await session.get(DailyCounter, today)
		return counter is None or counter.translated_count < limit



async def maybe_send_limit_warning(context: ContextTypes.DEFAULT_TYPE, group_id: int, chat_id: int) -> None:
	today = date.today()
	async with session_scope() as session:
		inserted = await session.scalar(
			pg_insert(GroupWarning)
			.values(group_id=group_id, date=today)
			.on_conflict_do_nothing(index_elements=[GroupWarning.group_id, GroupWarning.date])
			.returning(GroupWarning.id)
		)
		if inserted is None:
			return

	try:
		await context.bot.send_message(
			chat_id, "The daily translation limit has been reached. Translations will resume tomorrow."
		)
	except TelegramError:
		logger.info("Could not send limit-warning message to chat %s", chat_id)


async def maybe_handle_maintenance(context: ContextTypes.DEFAULT_TYPE, group_id: int, chat_id: int) -> bool:
	async with session_scope() as session:
		settings_row = await session.get(AppSettings, 1)
		if settings_row is None or not settings_row.maintenance_enabled:
			return False

		inserted = await session.scalar(
			pg_insert(GroupMaintenanceNotice)
			.values(group_id=group_id)
			.on_conflict_do_nothing(index_elements=[GroupMaintenanceNotice.group_id])
			.returning(GroupMaintenanceNotice.group_id)
		)
		if inserted is None:
			return True

		message_text = settings_row.maintenance_message or DEFAULT_MAINTENANCE_MESSAGE

	try:
		await context.bot.send_message(chat_id, message_text)
	except TelegramError:
		logger.info("Could not send maintenance notice to chat %s", chat_id)
	return True


async def resolve_translation_key(
	sender_telegram_id: int | None, group_id: int | None
) -> TranslationKey | None:
	async with session_scope() as session:
		if sender_telegram_id is not None:
			sender = await session.scalar(
				select(User).where(User.telegram_user_id == sender_telegram_id)
			)
			if sender is not None and sender.is_blocked:
				return None
			key = key_of(sender, owner_is_sender=True)
			if key is not None:
				return key

		if group_id is None:
			return None

		group = await session.get(Group, group_id)
		if group is None or group.owner_user_id is None:
			return None
		owner = await session.get(User, group.owner_user_id)
		if owner is not None and owner.is_blocked:
			return None
		return key_of(owner, owner_is_sender=False)


def key_of(user: User | None, owner_is_sender: bool) -> TranslationKey | None:
	if user is None or user.api_key_provider is None or user.api_key_encrypted is None:
		return None
	try:
		plain_key = decrypt_api_key(user.id, user.api_key_encrypted)
	except DecryptionError:
		logger.error(
			"Could not decrypt the stored key for user %s. If API_KEY_ENCRYPTION_KEY changed, "
			"every stored key is now unreadable and has to be set again.",
			user.id,
		)
		return None
	return TranslationKey(
		provider_code=user.api_key_provider,
		api_key=plain_key,
		owner_telegram_id=user.telegram_user_id,
		owner_is_sender=owner_is_sender,
	)


async def warn_missing_key(context: ContextTypes.DEFAULT_TYPE, message) -> None:
	private = message.chat.type == "private" if message.chat else False
	if private:
		await message.reply_text(MISSING_KEY_PRIVATE_MESSAGE)
		return

	if context.chat_data.get("missing_key_notice"):
		return
	context.chat_data["missing_key_notice"] = True
	try:
		await message.reply_text(MISSING_KEY_GROUP_MESSAGE)
	except TelegramError:
		logger.info("Could not send the missing-key notice")


async def notify_key_failure(
	context: ContextTypes.DEFAULT_TYPE, key: TranslationKey, group_title: str | None = None
) -> None:
	provider = get_provider(key.provider_code)
	label = provider.label if provider else key.provider_code
	where = f' in "{group_title}"' if group_title and not key.owner_is_sender else ""
	try:
		await context.bot.send_message(
			key.owner_telegram_id,
			f"Your {label} key didn't work for a translation{where}, so it didn't go through. "
			"Check it with /apikeystatus, or replace it with /setapikey.",
		)
	except TelegramError:
		logger.info("Could not notify user %s about the key failure", key.owner_telegram_id)


async def translate_for_message(
	context: ContextTypes.DEFAULT_TYPE,
	key: TranslationKey,
	group_id: int | None,
	group_limit: int | None,
	group_title: str | None,
	chat_id: int,
	text: str,
	target_lang: str,
	style: str | None = None,
) -> str | None:
	quota = QuotaTarget(group_id=group_id, group_limit=group_limit)
	if not await quota.take():
		if group_id is not None:
			await maybe_send_limit_warning(context, group_id, chat_id)
		return None

	try:
		return await translate_text(key.provider_code, key.api_key, text, target_lang, style=style)
	except UnknownLanguageError:
		await quota.give_back()
		logger.info("Refused an unknown target language for chat %s", chat_id)
		if not context.chat_data.get("unknown_language_notice"):
			context.chat_data["unknown_language_notice"] = True
			await send_quietly(context, chat_id, UNKNOWN_LANGUAGE_MESSAGE)
		return None
	except ProviderUnavailableError:
		await quota.give_back()
		logger.info("Provider was unavailable for chat %s", chat_id)
		await warn_translation_failed(context, chat_id)
		return None
	except PersonalKeyError:
		await quota.give_back()
		await notify_key_failure(context, key, group_title)
		return None
	except Exception:
		await quota.give_back()
		logger.exception("Translation failed for chat %s", chat_id)
		await warn_translation_failed(context, chat_id)
		return None


async def warn_translation_failed(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
	"""Tell the chat once per session that translations are failing, rather than going silent."""
	if context.chat_data.get("translation_failed_notice"):
		return
	context.chat_data["translation_failed_notice"] = True
	await send_quietly(context, chat_id, TRANSLATION_FAILED_MESSAGE)


async def send_quietly(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
	try:
		await context.bot.send_message(chat_id, text)
	except TelegramError:
		logger.info("Could not send a notice to chat %s", chat_id)
