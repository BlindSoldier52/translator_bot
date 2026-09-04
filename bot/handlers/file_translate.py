import logging
import os

from sqlalchemy import select
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.constants import (
	FILE_OUTPUT_MODE_FILE,
	FLOW_FILE_TRANSLATE_LANGUAGE,
	STEP_FILE_LANGUAGE,
)
from bot.handlers.common import clear_flow, join_words, max_file_bytes, split_for_telegram
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
from shared.files import (
	FileTranslationError,
	build_docx_file,
	build_pdf_file,
	build_srt_file,
	build_text_file,
	can_render_as_pdf,
	extract_content,
	group_pieces_into_batches,
	merge_translated_pieces,
	split_units_for_translation,
)
from shared.languages import UnknownLanguageError, resolve_language_code
from shared.models import Group, GroupFileDailyCounter, User
from shared.translation import PersonalKeyError, ProviderUnavailableError, translate_text_batch

logger = logging.getLogger(__name__)

LARGE_FILE_NOTICE_CHARS = 1500

NOT_ENABLED_MESSAGE = (
	"File translation isn't turned on for this group. The group admin can enable it with "
	"/filesettings in a private chat with me."
)
LIMIT_REACHED_MESSAGE = "Daily translation limit's been hit for today, try again tomorrow."
PROCESSING_MESSAGE = "Got it, translating your file now, this might take a moment."
EXTRACTION_FAILED_MESSAGE = (
	"Couldn't read that file, it might be corrupted or protected. Try a different file."
)
TRANSLATION_FAILED_MESSAGE = (
	"Couldn't finish translating that file, so I'm not sending back a half-broken result. "
	"Give it another go in a bit."
)
TOO_MUCH_TEXT_MESSAGE = (
	"That file has more text than I'll translate in one go. Split it into smaller files and "
	"send them one at a time."
)
NOT_ENOUGH_QUOTA_MESSAGE = (
	"That file needs more translations than are left for today. Try a smaller file, or come "
	"back tomorrow."
)
BUSY_MESSAGE = "I'm still working on your last one. Give me a moment and try again."
UNKNOWN_LANGUAGE_MESSAGE = (
	"I don't know that language. Send me a language name like Spanish, Japanese or Urdu, or /cancel."
)


async def handle_group_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	chat = update.effective_chat
	if message is None or chat is None or message.document is None:
		return
	if chat.type not in ("group", "supergroup"):
		return

	async with session_scope() as session:
		group = await session.scalar(select(Group).where(Group.telegram_chat_id == chat.id))
		if group is None or not group.is_active or group.is_blocked:
			return
		group_id = group.id
		group_title = group.title
		target_lang = group.primary_language
		enabled = group.file_translation_enabled
		allowed_extensions = list(group.file_allowed_extensions or [])
		max_size_mb = group.file_max_size_mb
		output_mode = group.file_output_mode
		uses_separate_limit = group.file_uses_separate_daily_limit
		file_daily_limit = group.file_daily_limit
		group_message_limit = group.daily_message_limit

	if not enabled:
		await send_once_per_chat(context, message, "file_translation_off_notice", NOT_ENABLED_MESSAGE)
		return

	document = message.document
	extension = extension_of(document.file_name)
	if not await check_extension(message, extension, allowed_extensions):
		return
	if not await check_size(message, document.file_size, max_size_mb):
		return

	if await maybe_handle_maintenance(context, group_id, chat.id):
		return

	if target_lang is None:
		await message.reply_text(
			"I don't know this group's main language yet, so I can't translate files here. "
			"An admin can set it with /setlanguage."
		)
		return

	sender_telegram_id = message.from_user.id if message.from_user else None
	key = await resolve_translation_key(sender_telegram_id, group_id)
	if key is None:
		await warn_missing_key(context, message)
		return

	quota = (
		QuotaTarget(group_id, file_daily_limit, GroupFileDailyCounter, always_count_group=True)
		if uses_separate_limit
		else QuotaTarget(group_id, group_message_limit)
	)
	if not await quota.take():
		await message.reply_text(LIMIT_REACHED_MESSAGE)
		return

	await process_document(
		context,
		message,
		key=key,
		quota=quota,
		file_id=document.file_id,
		file_name=document.file_name or f"file{extension}",
		extension=extension,
		target_lang=target_lang,
		output_mode=output_mode,
		group_title=group_title,
		max_bytes=size_ceiling(max_size_mb),
	)


async def handle_private_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	message = update.effective_message
	if message is None or message.document is None:
		return
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	active_flow = context.user_data.get("flow")
	if active_flow and active_flow.get("type") != FLOW_FILE_TRANSLATE_LANGUAGE:
		await message.reply_text(
			"Let's finish what we started first. Use /cancel if you'd rather translate that file now."
		)
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		if account is None:
			await message.reply_text(
				"You need an account first. Use /start to create one, then send me the file again."
			)
			return
		enabled = account.file_translation_enabled
		allowed_extensions = list(account.file_allowed_extensions or [])
		max_size_mb = account.file_max_size_mb

	if not enabled:
		await message.reply_text(
			"File translation isn't turned on for our chat yet. You can enable it with /filesettings."
		)
		return

	document = message.document
	extension = extension_of(document.file_name)
	if not await check_extension(message, extension, allowed_extensions, private=True):
		return
	if not await check_size(message, document.file_size, max_size_mb, private=True):
		return

	clear_flow(context.user_data)
	context.user_data["flow"] = {
		"type": FLOW_FILE_TRANSLATE_LANGUAGE,
		"step": STEP_FILE_LANGUAGE,
		"file_id": document.file_id,
		"file_name": document.file_name or f"file{extension}",
		"extension": extension,
		"max_size_mb": max_size_mb,
	}
	await message.reply_text(
		"Which language should I translate it into? Send me the language name, like Spanish. "
		"Use /cancel to stop."
	)


async def handle_file_language_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	message = update.effective_message
	target_lang = resolve_language_code(message.text or "")
	if target_lang is None:
		await message.reply_text(UNKNOWN_LANGUAGE_MESSAGE)
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		output_mode = account.file_output_mode if account else None

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

	await process_document(
		context,
		message,
		key=key,
		quota=quota,
		file_id=flow["file_id"],
		file_name=flow["file_name"],
		extension=flow["extension"],
		target_lang=target_lang,
		output_mode=output_mode,
		group_title=None,
		max_bytes=size_ceiling(flow.get("max_size_mb")),
	)


async def process_document(
	context: ContextTypes.DEFAULT_TYPE,
	message,
	*,
	key: TranslationKey,
	quota: QuotaTarget,
	file_id: str,
	file_name: str,
	extension: str,
	target_lang: str,
	output_mode: str,
	group_title: str | None,
	max_bytes: int,
) -> None:
	if context.user_data.get("translation_in_progress"):
		await quota.give_back()
		await message.reply_text(BUSY_MESSAGE)
		return

	context.user_data["translation_in_progress"] = True
	try:
		await translate_document(
			context,
			message,
			key=key,
			quota=quota,
			file_id=file_id,
			file_name=file_name,
			extension=extension,
			target_lang=target_lang,
			output_mode=output_mode,
			group_title=group_title,
			max_bytes=max_bytes,
		)
	finally:
		context.user_data.pop("translation_in_progress", None)


async def translate_document(
	context: ContextTypes.DEFAULT_TYPE,
	message,
	*,
	key: TranslationKey,
	quota: QuotaTarget,
	file_id: str,
	file_name: str,
	extension: str,
	target_lang: str,
	output_mode: str,
	group_title: str | None,
	max_bytes: int,
) -> None:
	data = await download_within_limit(context, message, file_id, max_bytes)
	if data is None:
		await quota.give_back()
		return

	try:
		content = extract_content(data, extension)
	except FileTranslationError as exc:
		await quota.give_back()
		await message.reply_text(str(exc))
		return
	except Exception:
		await quota.give_back()
		logger.exception("Unexpected extraction failure for %s", file_name)
		await message.reply_text(EXTRACTION_FAILED_MESSAGE)
		return
	finally:
		data = b""

	pieces, owners = split_units_for_translation(content.units)
	batches = group_pieces_into_batches(pieces)
	if len(batches) > get_settings().max_batches_per_file:
		await quota.give_back()
		await message.reply_text(TOO_MUCH_TEXT_MESSAGE)
		return

	extra_units = len(batches) - 1
	if extra_units > 0 and not await quota.take(extra_units):
		await quota.give_back()
		await message.reply_text(NOT_ENOUGH_QUOTA_MESSAGE)
		return

	if sum(len(unit) for unit in content.units) >= LARGE_FILE_NOTICE_CHARS:
		try:
			await message.reply_text(PROCESSING_MESSAGE)
		except TelegramError:
			logger.debug("Could not send the processing notice")

	try:
		translated_units = await translate_batches(
			context, key, batches, owners, len(content.units), target_lang, group_title
		)
	except UnknownLanguageError:
		await quota.give_back(len(batches))
		await message.reply_text(UNKNOWN_LANGUAGE_MESSAGE)
		return
	except FileTranslationError as exc:
		await quota.give_back(len(batches))
		await message.reply_text(str(exc))
		return
	except Exception:
		await quota.give_back(len(batches))
		logger.exception("File translation failed for %s", file_name)
		await message.reply_text(TRANSLATION_FAILED_MESSAGE)
		return

	if not any(unit.strip() for unit in translated_units):
		await message.reply_text(TRANSLATION_FAILED_MESSAGE)
		return

	if output_mode == FILE_OUTPUT_MODE_FILE:
		await deliver_as_file(message, translated_units, content.rebuild_context, extension, file_name)
		return

	await deliver_as_text(message, translated_units)


async def download_within_limit(
	context: ContextTypes.DEFAULT_TYPE,
	message,
	file_id: str,
	max_bytes: int,
	failure_message: str = EXTRACTION_FAILED_MESSAGE,
) -> bytes | None:
	try:
		telegram_file = await context.bot.get_file(file_id)
	except TelegramError:
		logger.exception("Could not fetch file %s", file_id)
		await message.reply_text(failure_message)
		return None

	if telegram_file.file_size is not None and telegram_file.file_size > max_bytes:
		await message.reply_text(
			f"That file's too big, the limit here is {max_bytes // (1024 * 1024)} MB."
		)
		return None

	try:
		data = bytes(await telegram_file.download_as_bytearray())
	except TelegramError:
		logger.exception("Could not download file %s", file_id)
		await message.reply_text(failure_message)
		return None

	if len(data) > max_bytes:
		await message.reply_text(
			f"That file's too big, the limit here is {max_bytes // (1024 * 1024)} MB."
		)
		return None
	return data


async def translate_batches(
	context: ContextTypes.DEFAULT_TYPE,
	key: TranslationKey,
	batches: list[list[str]],
	owners: list[int],
	unit_count: int,
	target_lang: str,
	group_title: str | None,
) -> list[str]:
	translated_pieces: list[str] = []

	for batch in batches:
		try:
			result = await translate_text_batch(key.provider_code, key.api_key, batch, target_lang)
		except ProviderUnavailableError as exc:
			logger.info("Provider was unavailable while translating a file: %s", exc)
			raise FileTranslationError(
				"The translation service didn't answer, so nothing was translated. Try again in a moment."
			) from exc
		except PersonalKeyError as exc:
			await notify_key_failure(context, key, group_title)
			raise FileTranslationError(
				"The API key didn't work for that file, so nothing was translated."
			) from exc
		translated_pieces.extend(result)

	return merge_translated_pieces(translated_pieces, owners, unit_count)


async def deliver_as_text(message, units: list[str]) -> None:
	text = "\n\n".join(unit for unit in units if unit.strip())
	chunks = split_for_telegram(f"Here's your translation:\n\n{text}")
	for chunk in chunks:
		try:
			await message.reply_text(chunk)
		except TelegramError:
			logger.exception("Could not send a translated chunk to chat %s", message.chat_id)
			return


async def deliver_as_file(
	message, units: list[str], rebuild_context, extension: str, file_name: str
) -> None:
	try:
		data = build_file(units, rebuild_context, extension)
	except FileTranslationError as exc:
		await message.reply_text(f"{exc} Here's the translation as text instead:")
		await deliver_as_text(message, units)
		return

	try:
		await message.reply_document(
			document=data, filename=f"translated_{file_name}", caption="Here's your translated file."
		)
	except TelegramError:
		logger.exception("Could not send the translated file to chat %s", message.chat_id)
		await message.reply_text("I translated it but couldn't send the file back. Here it is as text:")
		await deliver_as_text(message, units)
	finally:
		data = b""


def build_file(units: list[str], rebuild_context, extension: str) -> bytes:
	if extension == ".srt":
		return build_srt_file(units, rebuild_context)
	if extension == ".docx":
		return build_docx_file(units)
	if extension == ".pdf":
		if not can_render_as_pdf("\n\n".join(units)):
			raise FileTranslationError("I can't put that language into a PDF with the font I have.")
		return build_pdf_file(units)
	return build_text_file(units)


def extension_of(file_name: str | None) -> str:
	return os.path.splitext(file_name or "")[1].lower()


def size_ceiling(max_size_mb: int | None) -> int:
	if not max_size_mb:
		return max_file_bytes()
	return min(max_size_mb * 1024 * 1024, max_file_bytes())


async def check_extension(message, extension: str, allowed: list[str], private: bool = False) -> bool:
	if extension in allowed:
		return True
	where = "in our chat" if private else "in this group"
	supported = join_words(allowed) if allowed else "nothing at the moment"
	await message.reply_text(
		f"That file type isn't supported {where}. Supported types here: {supported}."
	)
	return False


async def check_size(message, file_size: int | None, max_size_mb: int, private: bool = False) -> bool:
	if file_size is not None and file_size > max_size_mb * 1024 * 1024:
		where = "for our chat" if private else "for this group"
		await message.reply_text(f"That file's too big {where}, current limit is {max_size_mb} MB.")
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
		logger.debug("Could not send %s to chat %s", marker, message.chat_id)
