import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache

from shared.images.errors import ImageTranslationError

logger = logging.getLogger(__name__)

TESSERACT_BINARY = "tesseract"
OCR_TIMEOUT_SECONDS = 90
LOW_CONFIDENCE_THRESHOLD = 60.0

OCR_FAILED_MESSAGE = "Couldn't process that image, it might be corrupted or too unclear to read."

TESSERACT_LANGUAGES = {
	"en": "eng",
	"ro": "ron",
	"es": "spa",
	"fr": "fra",
	"de": "deu",
	"it": "ita",
	"pt": "por",
	"ru": "rus",
	"uk": "ukr",
	"pl": "pol",
	"tr": "tur",
	"ar": "ara",
	"zh": "chi_sim",
	"ja": "jpn",
	"ko": "kor",
	"hi": "hin",
	"nl": "nld",
	"el": "ell",
	"sv": "swe",
	"bg": "bul",
	"cs": "ces",
	"hu": "hun",
	"he": "heb",
	"th": "tha",
	"vi": "vie",
}


LANGUAGE_SCRIPTS = {
	"ara": "Arabic",
	"bul": "Cyrillic",
	"ces": "Latin",
	"chi_sim": "HanS",
	"deu": "Latin",
	"ell": "Greek",
	"eng": "Latin",
	"fra": "Latin",
	"heb": "Hebrew",
	"hin": "Devanagari",
	"hun": "Latin",
	"ita": "Latin",
	"jpn": "Japanese",
	"kor": "Korean",
	"nld": "Latin",
	"pol": "Latin",
	"por": "Latin",
	"ron": "Latin",
	"rus": "Cyrillic",
	"spa": "Latin",
	"swe": "Latin",
	"tha": "Thai",
	"tur": "Latin",
	"ukr": "Cyrillic",
	"vie": "Latin",
}


@dataclass(frozen=True)
class OcrLine:
	text: str
	left: int
	top: int
	width: int
	height: int
	confidence: float


@dataclass(frozen=True)
class OcrResult:
	lines: list[OcrLine]
	confidence: float
	languages: str

	@property
	def text(self) -> str:
		return "\n".join(line.text for line in self.lines)

	@property
	def is_shaky(self) -> bool:
		return bool(self.lines) and self.confidence < LOW_CONFIDENCE_THRESHOLD


@lru_cache
def installed_languages() -> frozenset[str]:
	import subprocess

	try:
		result = subprocess.run(
			[TESSERACT_BINARY, "--list-langs"], capture_output=True, timeout=30, check=False
		)
	except (OSError, subprocess.SubprocessError) as exc:
		raise ImageTranslationError(OCR_FAILED_MESSAGE) from exc
	names = result.stdout.decode(errors="replace").splitlines()[1:]
	return frozenset(name.strip() for name in names if name.strip())


async def run_tesseract(data: bytes, arguments: list[str]) -> str:
	try:
		process = await asyncio.create_subprocess_exec(
			TESSERACT_BINARY,
			"stdin",
			"stdout",
			*arguments,
			stdin=asyncio.subprocess.PIPE,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)
	except OSError as exc:
		raise ImageTranslationError(OCR_FAILED_MESSAGE) from exc

	try:
		stdout, stderr = await asyncio.wait_for(process.communicate(data), OCR_TIMEOUT_SECONDS)
	except asyncio.TimeoutError as exc:
		process.kill()
		await process.wait()
		raise ImageTranslationError("That image took too long to read, try a smaller one.") from exc

	if process.returncode != 0:
		logger.info("tesseract failed: %s", stderr.decode(errors="replace")[:200])
		raise ImageTranslationError(OCR_FAILED_MESSAGE)
	return stdout.decode(errors="replace")


def installed_script_model(script: str) -> str | None:
	"""Tesseract lists script models either bare or under a script/ prefix, depending on tessdata."""
	available = installed_languages()
	for name in (script, f"script/{script}"):
		if name in available:
			return name
	return None


async def detect_script(data: bytes) -> str | None:
	try:
		output = await run_tesseract(data, ["--psm", "0", "-l", "osd"])
	except ImageTranslationError:
		return None

	for line in output.splitlines():
		if line.startswith("Script:"):
			script = line.split(":", 1)[1].strip()
			if installed_script_model(script) is None:
				logger.info("No installed OCR model for the %s script", script)
				return None
			return script
	return None


def resolve_languages(script: str | None, preferred_language: str | None) -> str:
	preferred = TESSERACT_LANGUAGES.get(preferred_language or "")
	preferred_is_available = bool(preferred) and preferred in installed_languages()

	# A single-language model beats the generic script model when the two agree.
	if preferred_is_available and (script is None or LANGUAGE_SCRIPTS.get(preferred) == script):
		return preferred
	if script:
		model = installed_script_model(script)
		if model is not None:
			return model
	if preferred_is_available:
		return preferred
	return "eng"


async def warm_models(language_codes: list[str | None]) -> None:
	from io import BytesIO

	from PIL import Image

	# installed_languages() shells out, so prime its cache off the event loop once, here,
	# rather than blocking whichever request happens to ask for it first.
	await asyncio.to_thread(installed_languages)

	buffer = BytesIO()
	Image.new("RGB", (32, 32), "white").save(buffer, "PNG")
	blank = buffer.getvalue()

	wanted = {"eng", "Latin"}
	for code in language_codes:
		name = TESSERACT_LANGUAGES.get(code or "")
		if name:
			wanted.add(name)

	available = installed_languages()
	wanted = {installed_script_model(name) or name for name in wanted}
	for name in sorted(wanted & available):
		try:
			await run_tesseract(blank, ["-l", name, "tsv"])
		except ImageTranslationError:
			logger.info("Could not warm up the %s OCR model", name)


async def read_image_text(data: bytes, preferred_language: str | None = None) -> OcrResult:
	script = await detect_script(data)
	languages = resolve_languages(script, preferred_language)
	tsv = await run_tesseract(data, ["-l", languages, "tsv"])
	lines = parse_tsv(tsv)
	confidences = [line.confidence for line in lines]
	average = sum(confidences) / len(confidences) if confidences else 0.0
	return OcrResult(lines=lines, confidence=average, languages=languages)


def parse_tsv(tsv: str) -> list[OcrLine]:
	grouped: dict[tuple[str, str, str], list[dict]] = {}
	for row in tsv.splitlines()[1:]:
		columns = row.split("\t")
		if len(columns) < 12:
			continue
		text = columns[11].strip()
		if not text:
			continue
		try:
			word = {
				"left": int(columns[6]),
				"top": int(columns[7]),
				"width": int(columns[8]),
				"height": int(columns[9]),
				"confidence": float(columns[10]),
				"text": text,
			}
		except ValueError:
			continue
		if word["confidence"] < 0:
			continue
		grouped.setdefault((columns[2], columns[3], columns[4]), []).append(word)

	lines = []
	for words in grouped.values():
		left = min(word["left"] for word in words)
		top = min(word["top"] for word in words)
		right = max(word["left"] + word["width"] for word in words)
		bottom = max(word["top"] + word["height"] for word in words)
		lines.append(
			OcrLine(
				text=" ".join(word["text"] for word in words),
				left=left,
				top=top,
				width=right - left,
				height=bottom - top,
				confidence=sum(word["confidence"] for word in words) / len(words),
			)
		)
	return sorted(lines, key=lambda line: (line.top, line.left))
