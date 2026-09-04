import logging
from dataclasses import dataclass

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.constants import (
	FILE_OUTPUT_MODE_FILE,
	FILE_OUTPUT_MODE_TEXT,
	FLOW_FILE_SETTINGS,
	IMAGE_OUTPUT_MODE_OVERLAY,
	IMAGE_OUTPUT_MODE_TEXT,
	MAX_ALLOWED_FILE_SIZE_MB,
	MAX_ALLOWED_IMAGE_SIZE_MB,
	STEP_FILE_CHOICE,
	STEP_FILE_DAILY_LIMIT,
	STEP_FILE_EXTENSIONS,
	STEP_FILE_LIMIT_MODE,
	STEP_FILE_MAX_SIZE,
	STEP_FILE_OUTPUT_MODE,
	STEP_FILE_SECTION,
	STEP_FILE_TARGET,
	STEP_IMAGE_DAILY_LIMIT,
	STEP_IMAGE_LIMIT_MODE,
	STEP_IMAGE_MAX_SIZE,
	STEP_IMAGE_OUTPUT_MODE,
)
from bot.handlers.common import clear_flow, join_words
from shared.db import session_scope
from shared.files import SUPPORTED_EXTENSIONS
from shared.models import AppSettings, Group, User

logger = logging.getLogger(__name__)

SCOPE_GROUP = "g"
SCOPE_PRIVATE = "u"

SECTION_FILES = "files"
SECTION_IMAGES = "images"

NO_GROUPS_MESSAGE = "You're not managing any group with this bot, so there's nothing to configure here."
PICK_GROUP_MESSAGE = "Which group are these settings for?"
PRIVATE_KEYWORD = "private"
DONE_MESSAGE = "All set. Send /filesettings whenever you want to change something."
SECTION_QUESTION = "What do you want to change? Send files or images, or done."


@dataclass
class FileSettingsView:
	scope: str
	target_id: int
	title: str
	enabled: bool
	extensions: list[str]
	max_size_mb: int
	output_mode: str
	uses_separate_daily_limit: bool
	daily_limit: int | None
	group_message_limit: int | None
	image_enabled: bool = False
	image_max_size_mb: int = 5
	image_output_mode: str = IMAGE_OUTPUT_MODE_TEXT
	image_uses_separate_daily_limit: bool = False
	image_daily_limit: int | None = None


async def filesettings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if update.effective_chat is None or update.effective_chat.type != "private":
		return

	telegram_user = update.effective_user
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user.id))
		if account is None:
			await update.message.reply_text(
				"You need an account first. Use /start to create one, then try /filesettings again."
			)
			return
		groups = (
			await session.scalars(
				select(Group)
				.where(Group.owner_user_id == account.id, Group.is_active.is_(True))
				.order_by(Group.title)
			)
		).all()
		group_choices = {group.title: group.id for group in groups}

	clear_flow(context.user_data)

	if not group_choices:
		view = await load_view(SCOPE_PRIVATE, telegram_user.id, telegram_user.id)
		start_section_step(context, SCOPE_PRIVATE, telegram_user.id)
		await update.message.reply_text(
			f"{NO_GROUPS_MESSAGE} You can still set up file and image translation for this "
			"private chat, though."
		)
		await update.message.reply_text(f"{describe_settings(view)}\n\n{SECTION_QUESTION}")
		return

	context.user_data["flow"] = {
		"type": FLOW_FILE_SETTINGS,
		"step": STEP_FILE_TARGET,
		"groups": group_choices,
	}
	names = join_words(list(group_choices), conjunction="or")
	await update.message.reply_text(
		f"{PICK_GROUP_MESSAGE} Send me {names}, or send {PRIVATE_KEYWORD} for this chat. "
		"Use /cancel to stop."
	)


async def load_view(scope: str, target_id: int, telegram_user_id: int) -> FileSettingsView | None:
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
		if account is None:
			return None

		if scope == SCOPE_PRIVATE:
			return FileSettingsView(
				scope=SCOPE_PRIVATE,
				target_id=account.telegram_user_id,
				title="this private chat",
				enabled=account.file_translation_enabled,
				extensions=list(account.file_allowed_extensions or []),
				max_size_mb=account.file_max_size_mb,
				output_mode=account.file_output_mode,
				uses_separate_daily_limit=False,
				daily_limit=None,
				group_message_limit=None,
				image_enabled=account.image_translation_enabled,
				image_max_size_mb=account.image_max_size_mb,
				image_output_mode=account.image_output_mode,
			)

		group = await session.get(Group, target_id)
		if group is None or group.owner_user_id != account.id:
			return None

		settings_row = await session.get(AppSettings, 1)
		return FileSettingsView(
			scope=SCOPE_GROUP,
			target_id=group.id,
			title=group.title,
			enabled=group.file_translation_enabled,
			extensions=list(group.file_allowed_extensions or []),
			max_size_mb=group.file_max_size_mb,
			output_mode=group.file_output_mode,
			uses_separate_daily_limit=group.file_uses_separate_daily_limit,
			daily_limit=group.file_daily_limit,
			group_message_limit=(
				group.daily_message_limit
				if group.daily_message_limit is not None
				else (settings_row.daily_message_limit if settings_row else None)
			),
			image_enabled=group.image_translation_enabled,
			image_max_size_mb=group.image_max_size_mb,
			image_output_mode=group.image_output_mode,
			image_uses_separate_daily_limit=group.image_uses_separate_daily_limit,
			image_daily_limit=group.image_daily_limit,
		)


def limit_sentence(view: FileSettingsView, separate: bool, limit: int | None, what: str) -> str:
	if not separate:
		shared = (
			f"the group's daily limit of {view.group_message_limit} translations"
			if view.group_message_limit
			else "the group's usual daily translation limit"
		)
		return f"{what} count against {shared}."
	if limit:
		return (
			f"{what} have their own limit of {limit} a day, kept separate from the group's "
			"normal translations."
		)
	return (
		f"{what} are set to have their own daily limit, but you haven't given me a number yet, "
		"so nothing is capping them."
	)


def describe_file_settings(view: FileSettingsView) -> str:
	sent_where = "here" if view.scope == SCOPE_PRIVATE else "there"
	if view.extensions:
		accepts = f"{join_words(view.extensions)} files up to {view.max_size_mb} MB"
	else:
		accepts = "no file types at all right now, so nothing would get through"

	if view.output_mode == FILE_OUTPUT_MODE_TEXT:
		answer = "I reply with the translated text right in the chat"
	else:
		answer = "I send back a translated file in the same format"

	if view.enabled:
		paragraphs = [f"File translation for {view.title} is on.", f"I accept {accepts}, and {answer}."]
	else:
		paragraphs = [
			f"File translation for {view.title} is off, so I ignore any file sent {sent_where}.",
			f"Turn it on and I'll accept {accepts}, and {answer}.",
		]

	if view.scope == SCOPE_GROUP:
		paragraphs.append(
			limit_sentence(view, view.uses_separate_daily_limit, view.daily_limit, "Files")
		)
	return "\n\n".join(paragraphs)


def describe_image_settings(view: FileSettingsView) -> str:
	sent_where = "here" if view.scope == SCOPE_PRIVATE else "there"
	if view.image_output_mode == IMAGE_OUTPUT_MODE_TEXT:
		answer = "I reply with the translated text"
	elif view.image_output_mode == IMAGE_OUTPUT_MODE_OVERLAY:
		answer = "I send back the image with the translation drawn over it"
	else:
		answer = "I reply with the translated text and then send the image with it drawn over"

	accepts = f"images up to {view.image_max_size_mb} MB"
	if view.image_enabled:
		paragraphs = [
			f"Image translation for {view.title} is on.",
			f"I read {accepts}, and {answer}.",
		]
	else:
		paragraphs = [
			f"Image translation for {view.title} is off, so I ignore any image sent {sent_where}.",
			f"Turn it on and I'll read {accepts}, and {answer}.",
		]

	if view.scope == SCOPE_GROUP:
		paragraphs.append(
			limit_sentence(
				view, view.image_uses_separate_daily_limit, view.image_daily_limit, "Images"
			)
		)
	return "\n\n".join(paragraphs)


def describe_settings(view: FileSettingsView | None) -> str:
	if view is None:
		return "I couldn't load those settings anymore. Try /filesettings again."
	return f"{describe_file_settings(view)}\n\n{describe_image_settings(view)}"


def choice_question(view: FileSettingsView | None, section: str) -> str:
	if view is None:
		return "Try /filesettings again."
	options = ["types", "size", "output"] if section == SECTION_FILES else ["size", "output"]
	if view.scope == SCOPE_GROUP:
		options.append("limit")
	enabled = view.enabled if section == SECTION_FILES else view.image_enabled
	options.append("off" if enabled else "on")
	options.extend(["back", "done"])
	return f"What do you want to change? Send {join_words(options, conjunction='or')}."


def start_section_step(context: ContextTypes.DEFAULT_TYPE, scope: str, target_id: int) -> None:
	context.user_data["flow"] = {
		"type": FLOW_FILE_SETTINGS,
		"step": STEP_FILE_SECTION,
		"scope": scope,
		"target_id": target_id,
	}


async def handle_file_settings_step(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> None:
	answer = " ".join((update.message.text or "").split())
	step = flow["step"]
	telegram_user_id = update.effective_user.id

	if step == STEP_FILE_TARGET:
		await handle_target_step(update, context, flow, answer, telegram_user_id)
		return

	scope, target_id = flow["scope"], flow["target_id"]
	view = await load_view(scope, target_id, telegram_user_id)
	if view is None:
		clear_flow(context.user_data)
		await update.message.reply_text("I couldn't load those settings anymore. Try /filesettings again.")
		return

	if step == STEP_FILE_SECTION:
		await handle_section_step(update, context, flow, answer, view)
		return

	if step == STEP_FILE_CHOICE:
		await handle_choice_step(update, context, flow, answer, view)
		return

	confirmation, next_step = await apply_value(scope, target_id, telegram_user_id, step, answer, view)
	if confirmation is None:
		await update.message.reply_text(f"{next_step} Or /cancel to stop.")
		return

	if next_step is not None:
		flow["step"] = next_step
		await update.message.reply_text(confirmation)
		return

	updated = await load_view(scope, target_id, telegram_user_id)
	flow["step"] = STEP_FILE_CHOICE
	await update.message.reply_text(f"{confirmation}\n\n{choice_question(updated, flow['section'])}")


async def handle_target_step(
	update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict, answer: str, telegram_user_id: int
) -> None:
	groups = flow.get("groups") or {}

	if answer.lower() == PRIVATE_KEYWORD:
		scope, target_id = SCOPE_PRIVATE, telegram_user_id
	else:
		matches = [title for title in groups if title.lower() == answer.lower()]
		if not matches:
			matches = [title for title in groups if answer.lower() and answer.lower() in title.lower()]
		if len(matches) != 1:
			names = join_words(list(groups), conjunction="or")
			trouble = "I don't have a group by that name" if not matches else "That matches more than one group"
			await update.message.reply_text(
				f"{trouble}. Send me {names}, or send {PRIVATE_KEYWORD} for this chat. Or /cancel to stop."
			)
			return
		scope, target_id = SCOPE_GROUP, groups[matches[0]]

	view = await load_view(scope, target_id, telegram_user_id)
	if view is None:
		clear_flow(context.user_data)
		await update.message.reply_text("You're not managing that group anymore. Try /filesettings again.")
		return

	start_section_step(context, scope, target_id)
	await update.message.reply_text(f"{describe_settings(view)}\n\n{SECTION_QUESTION}")


async def handle_section_step(
	update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict, answer: str, view: FileSettingsView
) -> None:
	choice = answer.lower()
	if choice in ("done", "stop", "nothing"):
		clear_flow(context.user_data)
		await update.message.reply_text(DONE_MESSAGE)
		return

	if choice in ("files", "file"):
		section, description = SECTION_FILES, describe_file_settings(view)
	elif choice in ("images", "image", "pictures", "photos"):
		section, description = SECTION_IMAGES, describe_image_settings(view)
	else:
		await update.message.reply_text(f"{SECTION_QUESTION} Or /cancel to stop.")
		return

	flow["section"] = section
	flow["step"] = STEP_FILE_CHOICE
	await update.message.reply_text(f"{description}\n\n{choice_question(view, section)}")


async def handle_choice_step(
	update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict, answer: str, view: FileSettingsView
) -> None:
	choice = answer.lower()
	section = flow.get("section", SECTION_FILES)
	images = section == SECTION_IMAGES

	if choice in ("done", "stop", "nothing"):
		clear_flow(context.user_data)
		await update.message.reply_text(DONE_MESSAGE)
		return

	if choice == "back":
		flow["step"] = STEP_FILE_SECTION
		await update.message.reply_text(f"{describe_settings(view)}\n\n{SECTION_QUESTION}")
		return

	if choice in ("on", "off"):
		enabled = choice == "on"
		field = "image_translation_enabled" if images else "file_translation_enabled"
		await save_setting(view.scope, view.target_id, update.effective_user.id, field, enabled)
		updated = await load_view(view.scope, view.target_id, update.effective_user.id)
		what = "Image translation" if images else "File translation"
		state = "on now" if enabled else "off now"
		await update.message.reply_text(
			f"{what} for {view.title} is {state}.\n\n{choice_question(updated, section)}"
		)
		return

	prompt = prompt_for(view, section, choice)
	if prompt is None:
		await update.message.reply_text(f"{choice_question(view, section)} Or /cancel to stop.")
		return

	step, message = prompt
	flow["step"] = step
	await update.message.reply_text(message)


def prompt_for(view: FileSettingsView, section: str, choice: str) -> tuple[str, str] | None:
	if section == SECTION_FILES:
		if choice == "types":
			current = (
				f"accepts {join_words(view.extensions)}" if view.extensions else "doesn't accept anything"
			)
			return (
				STEP_FILE_EXTENSIONS,
				"Send me the file types you want to allow, separated by spaces or commas. I can "
				f"handle {join_words(list(SUPPORTED_EXTENSIONS))}, and right now {view.title} {current}.",
			)
		if choice == "size":
			return (
				STEP_FILE_MAX_SIZE,
				"Send me the biggest file size you want to allow, as a plain number of MB between "
				f"1 and {MAX_ALLOWED_FILE_SIZE_MB}. It's {view.max_size_mb} MB right now.",
			)
		if choice == "output":
			return (
				STEP_FILE_OUTPUT_MODE,
				"Should I reply with the translated text in the chat, or send back a translated "
				"file? Send text or file.",
			)
		if choice == "limit" and view.scope == SCOPE_GROUP:
			return (
				STEP_FILE_LIMIT_MODE,
				"Should files count against the group's daily translation limit, or have their "
				"own limit? Send shared or separate.",
			)
		return None

	if choice == "size":
		return (
			STEP_IMAGE_MAX_SIZE,
			"Send me the biggest image size you want to allow, as a plain number of MB between 1 "
			f"and {MAX_ALLOWED_IMAGE_SIZE_MB}. It's {view.image_max_size_mb} MB right now.",
		)
	if choice == "output":
		return (
			STEP_IMAGE_OUTPUT_MODE,
			"Should I reply with the translated text, send the image back with the translation "
			"drawn over it, or do both? Send text, overlay or both.",
		)
	if choice == "limit" and view.scope == SCOPE_GROUP:
		return (
			STEP_IMAGE_LIMIT_MODE,
			"Should images count against the group's daily translation limit, or have their own "
			"limit? Send shared or separate.",
		)
	return None


async def apply_value(
	scope: str, target_id: int, telegram_user_id: int, step: str, answer: str, view: FileSettingsView
) -> tuple[str | None, str | None]:
	if step == STEP_FILE_EXTENSIONS:
		extensions, error = parse_extensions(answer)
		if error:
			return None, error
		await save_setting(scope, target_id, telegram_user_id, "file_allowed_extensions", extensions)
		return f"{view.title} now accepts {join_words(extensions)}.", None

	if step == STEP_FILE_MAX_SIZE:
		value, error = parse_positive_number(answer, MAX_ALLOWED_FILE_SIZE_MB)
		if error:
			return None, error
		await save_setting(scope, target_id, telegram_user_id, "file_max_size_mb", value)
		return f"The file size limit for {view.title} is now {value} MB.", None

	if step == STEP_IMAGE_MAX_SIZE:
		value, error = parse_positive_number(answer, MAX_ALLOWED_IMAGE_SIZE_MB)
		if error:
			return None, error
		await save_setting(scope, target_id, telegram_user_id, "image_max_size_mb", value)
		return f"The image size limit for {view.title} is now {value} MB.", None

	if step == STEP_FILE_OUTPUT_MODE:
		mode = answer.lower()
		if mode not in ("text", "file"):
			return None, "Send text if you want the translation in the chat, or file if you want a file back."
		value = FILE_OUTPUT_MODE_TEXT if mode == "text" else FILE_OUTPUT_MODE_FILE
		await save_setting(scope, target_id, telegram_user_id, "file_output_mode", value)
		if value == FILE_OUTPUT_MODE_TEXT:
			return "I'll reply with the translated text in the chat from now on.", None
		return "I'll send back a translated file from now on.", None

	if step == STEP_IMAGE_OUTPUT_MODE:
		mode = answer.lower()
		if mode not in ("text", "overlay", "both"):
			return None, "Send text, overlay or both."
		await save_setting(scope, target_id, telegram_user_id, "image_output_mode", mode)
		if mode == IMAGE_OUTPUT_MODE_TEXT:
			return "I'll reply with the translated text from now on.", None
		if mode == IMAGE_OUTPUT_MODE_OVERLAY:
			return "I'll send the image back with the translation drawn over it from now on.", None
		return "I'll reply with the text and send the image back with it drawn over, from now on.", None

	if step in (STEP_FILE_LIMIT_MODE, STEP_IMAGE_LIMIT_MODE):
		images = step == STEP_IMAGE_LIMIT_MODE
		mode = answer.lower()
		if mode not in ("shared", "separate", "same", "own"):
			return None, "Send shared to use the group's daily limit, or separate for their own."
		separate = mode in ("separate", "own")
		field = "image_uses_separate_daily_limit" if images else "file_uses_separate_daily_limit"
		await save_setting(scope, target_id, telegram_user_id, field, separate)
		what = "Images" if images else "Files"
		current = view.image_daily_limit if images else view.daily_limit
		if not separate:
			return f"{what} in {view.title} count against the group's daily limit again.", None
		if current:
			return f"{what} in {view.title} have their own limit of {current} a day.", None
		return (
			f"{what} in {view.title} have their own limit now. How many a day? Send me a plain number.",
			STEP_IMAGE_DAILY_LIMIT if images else STEP_FILE_DAILY_LIMIT,
		)

	if step in (STEP_FILE_DAILY_LIMIT, STEP_IMAGE_DAILY_LIMIT):
		value, error = parse_positive_number(answer)
		if error:
			return None, error
		images = step == STEP_IMAGE_DAILY_LIMIT
		field = "image_daily_limit" if images else "file_daily_limit"
		await save_setting(scope, target_id, telegram_user_id, field, value)
		what = "images" if images else "files"
		return f"{view.title} can translate {value} {what} a day now.", None

	return None, "I lost track of that. Try /filesettings again."


def parse_extensions(text: str) -> tuple[list[str] | None, str | None]:
	tokens = [token for token in text.lower().replace(",", " ").split() if token]
	if not tokens:
		return None, (
			"That would leave no file types allowed, which quietly turns file translation off. "
			"Send me at least one type, or send off to turn the whole thing off."
		)

	extensions: list[str] = []
	for token in tokens:
		extension = token if token.startswith(".") else f".{token}"
		if extension not in SUPPORTED_EXTENSIONS:
			return None, f"I can't handle {extension}. I can read {join_words(list(SUPPORTED_EXTENSIONS))}."
		if extension not in extensions:
			extensions.append(extension)
	return extensions, None


def parse_positive_number(text: str, maximum: int | None = None) -> tuple[int | None, str | None]:
	try:
		value = int(text.strip())
	except ValueError:
		return None, "That's not a number. Send me a plain number, like 5."
	if value <= 0:
		return None, "That has to be a positive number, zero or less won't work."
	if maximum is not None and value > maximum:
		return None, f"Telegram won't let me download anything bigger than {maximum} MB, so that's the ceiling."
	return value, None


async def save_setting(scope: str, target_id: int, telegram_user_id: int, field: str, value) -> bool:
	async with session_scope() as session:
		account = await session.scalar(select(User).where(User.telegram_user_id == telegram_user_id))
		if account is None:
			return False

		if scope == SCOPE_PRIVATE:
			target = account
		else:
			target = await session.get(Group, target_id)
			if target is None or target.owner_user_id != account.id:
				return False

		if not hasattr(target, field):
			return False
		setattr(target, field, value)
		return True
