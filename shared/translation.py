import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from lingua import Language, LanguageDetectorBuilder

from shared.languages import require_language_name, resolve_language_code, resolve_style
from shared.providers import ProviderAuthError, ProviderError, get_provider

logger = logging.getLogger(__name__)


class PersonalKeyError(Exception):
	"""The user's own API key is what failed, so it is worth telling them to replace it."""


class ProviderUnavailableError(PersonalKeyError):
	"""The provider call failed for a reason that has nothing to do with the key."""


def wrap_provider_error(exc: ProviderError) -> PersonalKeyError:
	if isinstance(exc, ProviderAuthError):
		return PersonalKeyError(str(exc))
	return ProviderUnavailableError(str(exc))


COMMON_LANGUAGES: dict[str, str] = {
	"en": "English",
	"ro": "Romanian",
	"es": "Spanish",
	"fr": "French",
	"de": "German",
	"it": "Italian",
	"pt": "Portuguese",
	"ru": "Russian",
	"uk": "Ukrainian",
	"pl": "Polish",
	"tr": "Turkish",
	"ar": "Arabic",
	"zh": "Chinese",
	"ja": "Japanese",
	"ko": "Korean",
	"hi": "Hindi",
}

DETECTOR_LANGUAGES = [
	Language.ENGLISH,
	Language.ROMANIAN,
	Language.SPANISH,
	Language.FRENCH,
	Language.GERMAN,
	Language.ITALIAN,
	Language.PORTUGUESE,
	Language.RUSSIAN,
	Language.UKRAINIAN,
	Language.POLISH,
	Language.TURKISH,
	Language.ARABIC,
	Language.CHINESE,
	Language.JAPANESE,
	Language.KOREAN,
	Language.HINDI,
	Language.DUTCH,
	Language.GREEK,
	Language.SWEDISH,
	Language.BULGARIAN,
	Language.CZECH,
	Language.HUNGARIAN,
]

LOCAL_CONFIDENCE_THRESHOLD = 0.85


@lru_cache
def detector():
	return (
		LanguageDetectorBuilder.from_languages(*DETECTOR_LANGUAGES)
		.with_preloaded_language_models()
		.build()
	)


@dataclass(frozen=True)
class LanguageDetectionResult:
	lang_code: str
	confidence: float
	source: str


def detect_locally(text: str) -> LanguageDetectionResult | None:
	values = detector().compute_language_confidence_values(text)
	if not values:
		return None
	top_language, confidence = values[0].language, values[0].value
	if confidence <= 0:
		return None
	return LanguageDetectionResult(
		lang_code=top_language.iso_code_639_1.name.lower(),
		confidence=confidence,
		source="local",
	)


def require_provider(provider_code: str):
	provider = get_provider(provider_code)
	if provider is None:
		raise PersonalKeyError(f"Unknown provider: {provider_code}")
	return provider


async def detect_language(
	text: str, provider_code: str | None = None, api_key: str | None = None
) -> LanguageDetectionResult | None:
	cleaned = " ".join(text.split())
	if len(cleaned) < 2:
		return None

	local_result = detect_locally(cleaned)
	if local_result is not None and local_result.confidence >= LOCAL_CONFIDENCE_THRESHOLD:
		return local_result
	if provider_code is None or api_key is None:
		return local_result

	try:
		provider = require_provider(provider_code)
		code = (await provider.detect_language(api_key, cleaned)).strip().lower()
	except (ProviderError, PersonalKeyError):
		logger.info("Provider language-detection fallback failed, using the local guess")
		return local_result

	if code == "unk" or len(code) != 2:
		return None
	return LanguageDetectionResult(lang_code=code, confidence=1.0, source="provider")


@dataclass(frozen=True)
class TranslationRequest:
	text: str | None
	language: str | None
	needs_context: bool
	explain: bool
	style: str | None


JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


async def detect_translation_request(
	provider_code: str, api_key: str, text: str
) -> TranslationRequest | None:
	provider = require_provider(provider_code)
	try:
		reply = await provider.parse_translation_request(api_key, text)
	except ProviderError as exc:
		raise wrap_provider_error(exc) from exc

	match = JSON_OBJECT_RE.search(reply.strip())
	if match is None:
		return None
	try:
		data = json.loads(match.group(0))
	except json.JSONDecodeError:
		return None

	if not data.get("is_request"):
		return None

	language = data.get("language")
	if language is not None and not isinstance(language, str):
		language = None

	style = data.get("style")
	if style is not None and not isinstance(style, str):
		style = None

	return TranslationRequest(
		text=data.get("text") or None,
		language=resolve_language_code(language),
		needs_context=bool(data.get("needs_context")),
		explain=bool(data.get("explain")),
		style=resolve_style(style),
	)


async def explain_term(provider_code: str, api_key: str, text: str) -> str:
	provider = require_provider(provider_code)
	try:
		return (await provider.explain_term(api_key, text)).strip()
	except ProviderError as exc:
		raise wrap_provider_error(exc) from exc


async def translate_text(
	provider_code: str, api_key: str, text: str, target_lang_code: str, style: str | None = None
) -> str:
	target_name = require_language_name(target_lang_code)
	provider = require_provider(provider_code)
	try:
		return await provider.translate(api_key, text, target_name, style=resolve_style(style))
	except ProviderError as exc:
		raise wrap_provider_error(exc) from exc


async def translate_text_batch(
	provider_code: str, api_key: str, units: list[str], target_lang_code: str
) -> list[str]:
	if not units:
		return []
	target_name = require_language_name(target_lang_code)
	provider = require_provider(provider_code)
	try:
		return await provider.translate_batch(api_key, units, target_name)
	except ProviderError as exc:
		raise wrap_provider_error(exc) from exc
