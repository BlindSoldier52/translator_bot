from io import BytesIO

from shared.font import pick_font_path
from shared.images.errors import ImageTranslationError
from shared.images.ocr import OcrLine

MIN_FONT_SIZE = 11
BOX_PADDING = 4
BOX_ALPHA = 235


def build_overlay_image(data: bytes, lines: list[OcrLine], translations: list[str]) -> bytes:
	from PIL import Image, ImageDraw

	if len(lines) != len(translations):
		raise ImageTranslationError("Couldn't line the translation up with the image.")

	try:
		original = Image.open(BytesIO(data))
		original.load()
	except Exception as exc:
		raise ImageTranslationError("Couldn't open that image to draw on it.") from exc

	image_format = (original.format or "PNG").upper()
	canvas = original.convert("RGBA")
	overlay = Image.new("RGBA", canvas.size, (255, 255, 255, 0))
	draw = ImageDraw.Draw(overlay)
	font_path = pick_font_path(" ".join(translations))

	for line, translation in zip(lines, translations):
		text = translation.strip()
		if not text:
			continue
		draw_line(draw, line, text, font_path, canvas.size)

	combined = Image.alpha_composite(canvas, overlay)
	buffer = BytesIO()
	if image_format in ("JPEG", "JPG"):
		combined.convert("RGB").save(buffer, "JPEG", quality=92)
	else:
		combined.save(buffer, "PNG")
	return buffer.getvalue()


def draw_line(draw, line: OcrLine, text: str, font_path: str, canvas_size: tuple[int, int]) -> None:
	box_left = max(line.left - BOX_PADDING, 0)
	box_top = max(line.top - BOX_PADDING, 0)
	box_right = min(line.left + line.width + BOX_PADDING, canvas_size[0])
	box_bottom = min(line.top + line.height + BOX_PADDING, canvas_size[1])
	available_width = max(box_right - box_left - 2 * BOX_PADDING, 1)

	font, wrapped, text_height = fit_text(text, font_path, available_width, max(line.height, MIN_FONT_SIZE))
	needed_height = text_height + 2 * BOX_PADDING
	if box_top + needed_height > canvas_size[1]:
		box_top = max(canvas_size[1] - needed_height, 0)
	box_bottom = min(box_top + needed_height, canvas_size[1])

	draw.rectangle([box_left, box_top, box_right, box_bottom], fill=(255, 255, 255, BOX_ALPHA))
	draw.multiline_text(
		(box_left + BOX_PADDING, box_top + BOX_PADDING),
		"\n".join(wrapped),
		font=font,
		fill=(15, 15, 15, 255),
		spacing=2,
	)


def fit_text(text: str, font_path: str, available_width: int, line_height: int):
	size = max(int(line_height * 0.85), MIN_FONT_SIZE)
	while size > MIN_FONT_SIZE:
		font = load_font(font_path, size)
		if measure(font, text) <= available_width:
			return font, [text], text_height(font, [text])
		size -= 1

	font = load_font(font_path, MIN_FONT_SIZE)
	wrapped = wrap(font, text, available_width)
	return font, wrapped, text_height(font, wrapped)


def load_font(font_path: str, size: int):
	from PIL import ImageFont

	try:
		return ImageFont.truetype(font_path, size)
	except OSError as exc:
		raise ImageTranslationError("I don't have a font I can write that language with.") from exc


def measure(font, text: str) -> int:
	left, _, right, _ = font.getbbox(text)
	return right - left


def text_height(font, lines: list[str]) -> int:
	ascent, descent = font.getmetrics()
	return (ascent + descent + 2) * len(lines)


def wrap(font, text: str, available_width: int) -> list[str]:
	words = text.split()
	if not words:
		return [text]

	lines: list[str] = []
	current = words[0]
	for word in words[1:]:
		candidate = f"{current} {word}"
		if measure(font, candidate) <= available_width:
			current = candidate
		else:
			lines.append(current)
			current = word
	lines.append(current)
	return lines
