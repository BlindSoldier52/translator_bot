from shared.files.errors import FileTranslationError
from shared.files.pdf_font import FONT_NAME, FONT_PATH


def build_text_file(units: list[str]) -> bytes:
	return "\n\n".join(units).encode("utf-8")


def build_docx_file(units: list[str]) -> bytes:
	from io import BytesIO

	from docx import Document

	document = Document()
	for unit in units:
		document.add_paragraph(unit)

	buffer = BytesIO()
	document.save(buffer)
	return buffer.getvalue()


def build_srt_file(units: list[str], rebuild_context) -> bytes:
	import srt as srt_lib

	subtitles = rebuild_context
	if subtitles is None or len(subtitles) != len(units):
		raise FileTranslationError("Couldn't rebuild that subtitle file, the translation didn't line up.")

	rebuilt = [
		srt_lib.Subtitle(
			index=subtitle.index,
			start=subtitle.start,
			end=subtitle.end,
			content=translated.strip() or subtitle.content,
			proprietary=subtitle.proprietary,
		)
		for subtitle, translated in zip(subtitles, units)
	]
	return srt_lib.compose(rebuilt, reindex=False).encode("utf-8")


def build_pdf_file(units: list[str]) -> bytes:
	from fpdf import FPDF

	text = "\n\n".join(units)
	pdf = FPDF()
	pdf.add_page()
	try:
		pdf.add_font(FONT_NAME, "", FONT_PATH)
	except (RuntimeError, OSError) as exc:
		raise FileTranslationError("PDF generation isn't available right now.") from exc
	pdf.set_font(FONT_NAME, size=12)
	pdf.multi_cell(0, 8, text)
	return bytes(pdf.output())
