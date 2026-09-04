import logging

from sqlalchemy import select
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.constants import (
	FLOW_IMAGE_TRANSLATE_LANGUAGE,
	IMAGE_OUTPUT_MODE_BOTH,
	IMAGE_OUTPUT_MODE_OVERLAY,
	IMAGE_OUTPUT_MODE_TEXT,
	STEP_IMAGE_LANGUAGE,
)
from bot.handlers.common import clear_flow, split_for_telegram
from bot.handlers.file_translate import (
	BUSY_MESSAGE,
	LIMIT_REACHED_MESSAGE,
	download_within_limit,
	size_ceiling,
)
from bot.handlers.translate import (
	QuotaTarget,
	TranslationKey,
	maybe_handle_maintenance,
	notify_key_failure,
	resolve_translation_key,
	warn_missing_key,
)
from shared.config import get_settings
from shared.db import session_scope
from shared.files import group_pieces_into_batches
from shared.images import ImageTranslationError, build_overlay_image, read_image_text
from shared.languages import UnknownLanguageError, resolve_language_code
from shared.models import Group, GroupImageDailyCounter, User
from shared.translation import PersonalKeyError, ProviderUnavailableError, translate_text_batch

logger = logging.getLogger(__name__)

NOT_ENABLED_MESSAGE = (
	"Image translation isn't turned on for this group. The group admin can enable it with "
	"/filesettings in a private chat with me."
)
NOT_ENABLED_PRIVATE_MESSAGE = (
	"Image translation isn't turned on for our chat yet. You can enable it with /filesettings."
)
PROCESSING_MESSAGE = "Reading the image now, one sec."
DOWNLOAD_FAILED_MESSAGE = "Couldn't fetch that image, try sending it again."
NO_TEXT_MESSAGE = "Couldn't find any readable text in that image."
TRANSLATION_FAILED_MESSAGE = (
	"Couldn't finish translating that image, so I'm not sending back a half-broken result. "
	"Give it another go in a bit."
)
TOO_MUCH_TEXT_MESSAGE = (
	"There's more text in that image than I'll translate in one go. Try a smaller crop."
)
NOT_ENOUGH_QUOTA_MESSAGE = (
	"That image needs more translations than are left for today. Come back tomorrow."
)
UNKNOWN_LANGUAGE_MESSAGE = (
	"I don't know that language. Send me a language name like Spanish, Japanese or Urdu, or /cancel."
)
SHAKY_NOTE = "The text was hard to read, so this might not be exact."
TEXT_PREFIX = "Here's what it says, translated:"
OVERLAY_CAPTION = "Here's the image with the translation."


async def handle_group_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	chat = update.effective_chat
	if message is None or chat is None or chat.type not in ("group", "supergroup"):
		return

	source = image_source(message)
	if source is None:
		return

	async with session_scope() as session:
		group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat.id))
		if group is None or not group.is_active or group.is_blocked:
			return
		group_id = group.id
		group_title = group.title
		source_language = group.primary_language
		enabled = group.image_translation_enabled
		max_size_mb = group.image_max_size_mb
		output_mode = group.image_output_mode
		uses_separate_limit = group.image_uses_separate_daily_limit
		image_daily_limit = group.image_daily_limit
		group_message_limit = group.daily_message_limit

	if not enabled:
		await send_once_per_chat(context, message, "image_translation_off_notice", NOT_ENABLED_MESSAGE)
		return

	file_id, file_size = source
	if not await check_size(message, file_size, max_size_mb):
		return

	if await maybe_handle_maintenance(context, group_id, chat.id):
		return

	if source_language is None:
		await message.reply_text(
			"I don't know this group's main language yet, so I don't know what to translate that "
			"image into. An admin can set it with /setlanguage."
		)
		return

	sender_telegram_id = message.from_user.id if message.from_user else None
	key = await resolve_translation_key(sender_telegram_id, group_id)
	if key is None:
		await warn_missing_key(context, message)
		return

	quota = (
		QuotaTarget(group_id, image_daily_limit, GroupImageDailyCounter, always_count_group=True)
		if uses_separate_limit
		else QuotaTarget(group_id, group_message_limit)
	)
	if not await quota.take():
		await message.reply_text(LIMIT_REACHED_MESSAGE)
		return

	await process_image(
		context,
		message,
		key=key,
		quota=quota,
		file_id=file_id,
		target_lang=source_language,
		output_mode=output_mode,
		source_language=source_language,
		group_title=group_title,
		max_bytes=size_ceiling(max_size_mb),
	)


async def handle_private_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	if message is None or update.effective_chat is None or update.effective_chat.type != "private":
		return

	source = image_source(message)
	if source is None:
		return

	active_flow = context.user_data.get("flow")
	if active_flow and active_flow.get("type") != FLOW_IMAGE_TRANSLATE_LANGUAGE:
		await message.reply_text(
			"Let's finish what we started first. Use /cancel if you'd rather translate that image now."
		)
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		if account is None:
			await message.reply_text(
				"You need an account first. Use /start to create one, then send me the image again."
			)
			return
		enabled = account.image_translation_enabled
		max_size_mb = account.image_max_size_mb

	if not enabled:
		await message.reply_text(NOT_ENABLED_PRIVATE_MESSAGE)
		return

	file_id, file_size = source
	if not await check_size(message, file_size, max_size_mb, private=True):
		return

	clear_flow(context.user_data)
	context.user_data["flow"] = {
		"type": FLOW_IMAGE_TRANSLATE_LANGUAGE,
		"step": STEP_IMAGE_LANGUAGE,
		"file_id": file_id,
		"max_size_mb": max_size_mb,
	}
	await message.reply_text(
		"Which language should I translate it into? Send me the language name, like Spanish. "
		"Use /cancel to stop."
	)


async def handle_image_language_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	message = update.effective_message
	target_lang = resolve_language_code(message.text or "")
	if target_lang is None:
		await message.reply_text(UNKNOWN_LANGUAGE_MESSAGE)
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		output_mode = account.image_output_mode if account else None

	clear_flow(context.user_data)
	if output_mode is None:
		await message.reply_text("I couldn't find your account. Use /start first.")
		return

	key = await resolve_translation_key(telegram_user.id, None)
	if key is None:
		await warn_missing_key(context, message)
		return

	quota = QuotaTarget()
	if not await quota.take():
		await message.reply_text(LIMIT_REACHED_MESSAGE)
		return

	await process_image(
		context,
		message,
		key=key,
		quota=quota,
		file_id=flow["file_id"],
		target_lang=target_lang,
		output_mode=output_mode,
		source_language=None,
		group_title=None,
		max_bytes=size_ceiling(flow.get("max_size_mb")),
	)


async def process_image(
	context: ContextTypes.DEFAULT_TYPE,
	message,
	*,
	key: TranslationKey,
	quota: QuotaTarget,
	file_id: str,
	target_lang: str,
	output_mode: str,
	source_language: str | None,
	group_title: str | None,
	max_bytes: int,
) -> None:
	if context.user_data.get("translation_in_progress"):
		await quota.give_back()
		await message.reply_text(BUSY_MESSAGE)
		return

	context.user_data["translation_in_progress"] = True
	try:
		await translate_image(
			context,
			message,
			key=key,
			quota=quota,
			file_id=file_id,
			target_lang=target_lang,
			output_mode=output_mode,
			source_language=source_language,
			group_title=group_title,
			max_bytes=max_bytes,
		)
	finally:
		context.user_data.pop("translation_in_progress", None)


async def translate_image(
	context: ContextTypes.DEFAULT_TYPE,
	message,
	*,
	key: TranslationKey,
	quota: QuotaTarget,
	file_id: str,
	target_lang: str,
	output_mode: str,
	source_language: str | None,
	group_title: str | None,
	max_bytes: int,
) -> None:
	data = await download_within_limit(
		context, message, file_id, max_bytes, DOWNLOAD_FAILED_MESSAGE
	)
	if data is None:
		await quota.give_back()
		return

	try:
		await message.reply_text(PROCESSING_MESSAGE)
	except TelegramError:
		logger.debug("Could not send the processing notice")

	try:
		result = await read_image_text(data, source_language)
	except ImageTranslationError as exc:
		await quota.give_back()
		await message.reply_text(str(exc))
		return
	except Exception:
		await quota.give_back()
		logger.exception("OCR failed unexpectedly")
		await message.reply_text("Couldn't process that image, it might be corrupted or too unclear to read.")
		return

	if not result.lines:
		await quota.give_back()
		await message.reply_text(NO_TEXT_MESSAGE)
		return

	batches = group_pieces_into_batches([" ".join(line.text.split()) for line in result.lines])
	if len(batches) > get_settings().max_batches_per_image:
		await quota.give_back()
		await message.reply_text(TOO_MUCH_TEXT_MESSAGE)
		return

	extra_units = len(batches) - 1
	if extra_units > 0 and not await quota.take(extra_units):
		await quota.give_back()
		await message.reply_text(NOT_ENOUGH_QUOTA_MESSAGE)
		return

	try:
		translations = await translate_batches(context, key, batches, target_lang, group_title)
	except UnknownLanguageError:
		await quota.give_back(len(batches))
		await message.reply_text(UNKNOWN_LANGUAGE_MESSAGE)
		return
	except ImageTranslationError as exc:
		await quota.give_back(len(batches))
		await message.reply_text(str(exc))
		return
	except Exception:
		await quota.give_back(len(batches))
		logger.exception("Image translation failed")
		await message.reply_text(TRANSLATION_FAILED_MESSAGE)
		return

	if not any(translation.strip() for translation in translations):
		await message.reply_text(TRANSLATION_FAILED_MESSAGE)
		return

	if output_mode in (IMAGE_OUTPUT_MODE_TEXT, IMAGE_OUTPUT_MODE_BOTH):
		await deliver_text(message, translations, result.is_shaky)

	if output_mode in (IMAGE_OUTPUT_MODE_OVERLAY, IMAGE_OUTPUT_MODE_BOTH):
		await deliver_overlay(message, data, result, translations, output_mode)

	data = b""


async def translate_batches(
	context: ContextTypes.DEFAULT_TYPE,
	key: TranslationKey,
	batches: list[list[str]],
	target_lang: str,
	group_title: str | None,
) -> list[str]:
	translations: list[str] = []
	for batch in batches:
		try:
			translations.extend(
				await translate_text_batch(key.provider_code, key.api_key, batch, target_lang)
			)
		except ProviderUnavailableError as exc:
			logger.info("Provider was unavailable while translating an image: %s", exc)
			raise ImageTranslationError(
				"The translation service didn't answer, so nothing was translated. Try again in a moment."
			) from exc
		except PersonalKeyError as exc:
			await notify_key_failure(context, key, group_title)
			raise ImageTranslationError(
				"The API key didn't work for that image, so nothing was translated."
			) from exc
	return translations


async def deliver_text(message, translations: list[str], shaky: bool) -> None:
	body = "\n".join(translation for translation in translations if translation.strip())
	prefix = f"{TEXT_PREFIX}\n\n" if not shaky else f"{SHAKY_NOTE}\n\n{TEXT_PREFIX}\n\n"
	for chunk in split_for_telegram(f"{prefix}{body}"):
		try:
			await message.reply_text(chunk)
		except TelegramError:
			logger.exception("Could not send the translated image text")
			return


async def deliver_overlay(message, data: bytes, result, translations: list[str], output_mode: str) -> None:
	try:
		overlaid = build_overlay_image(data, result.lines, translations)
	except ImageTranslationError as exc:
		await message.reply_text(f"{exc} Here's the translation as text instead:")
		if output_mode == IMAGE_OUTPUT_MODE_OVERLAY:
			await deliver_text(message, translations, result.is_shaky)
		return

	try:
		await message.reply_photo(photo=overlaid, caption=OVERLAY_CAPTION)
	except TelegramError:
		logger.exception("Could not send the overlaid image")
		await message.reply_text("I translated it but couldn't send the image back.")
		if output_mode == IMAGE_OUTPUT_MODE_OVERLAY:
			await deliver_text(message, translations, result.is_shaky)


def image_source(message) -> tuple[str, int | None] | None:
	if message.photo:
		largest = message.photo[-1]
		return largest.file_id, largest.file_size
	document = message.document
	if document is not None and (document.mime_type or "").startswith("image/"):
		return document.file_id, document.file_size
	return None


async def check_size(message, file_size: int | None, max_size_mb: int, private: bool = False) -> bool:
	if file_size is not None and file_size > max_size_mb * 1024 * 1024:
		where = "for our chat" if private else "for this group"
		await message.reply_text(f"That image's too big {where}, current limit is {max_size_mb} MB.")
		return False
	return True


async def send_once_per_chat(
	context: ContextTypes.DEFAULT_TYPE, message, marker: str, text: str
) -> None:
	if context.chat_data.get(marker):
		return
	context.chat_data[marker] = True
	try:
		await message.reply_text(text)
	except TelegramError:
		logger.debug("Could not send %s", marker)
