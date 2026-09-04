from functools import lru_cache

from shared.files.errors import FileTranslationError
from shared.font import FONT_PATH

FONT_NAME = "DejaVu"

__all__ = ["FONT_NAME", "FONT_PATH", "can_render_as_pdf"]


@lru_cache
def font_cmap() -> dict:
	from fpdf import FPDF

	pdf = FPDF()
	try:
		pdf.add_font(FONT_NAME, "", FONT_PATH)
	except (RuntimeError, OSError) as exc:
		raise FileTranslationError("PDF generation isn't available right now.") from exc
	font = pdf.fonts[FONT_NAME.lower()]
	return font.cmap


UNSHAPEABLE_RANGES = (
	(0x0600, 0x06FF),  # Arabic
	(0x0750, 0x077F),  # Arabic Supplement
	(0xFB50, 0xFEFF),  # Arabic Presentation Forms
)


def needs_text_shaping(char: str) -> bool:
	code = ord(char)
	return any(start <= code <= end for start, end in UNSHAPEABLE_RANGES)


def can_render_as_pdf(text: str) -> bool:
	cmap = font_cmap()
	for char in text:
		if char.isspace():
			continue
		if needs_text_shaping(char):
			return False
		if ord(char) not in cmap:
			return False
	return True
