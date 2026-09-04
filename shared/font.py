FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

SCRIPT_FONTS: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
	(
		"/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
		((0x2E80, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF)),
	),
	("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf", ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFEFF))),
	("/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf", ((0x0590, 0x05FF),)),
	("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", ((0x0900, 0x097F),)),
	("/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf", ((0x0E00, 0x0E7F),)),
	("/usr/share/fonts/truetype/noto/NotoSansGeorgian-Regular.ttf", ((0x10A0, 0x10FF),)),
	("/usr/share/fonts/truetype/noto/NotoSansArmenian-Regular.ttf", ((0x0530, 0x058F),)),
	("/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf", ((0x1200, 0x137F),)),
)


def pick_font_path(text: str) -> str:
	import os

	counts: dict[str, int] = {}
	for char in text:
		code = ord(char)
		for path, ranges in SCRIPT_FONTS:
			if any(start <= code <= end for start, end in ranges):
				counts[path] = counts.get(path, 0) + 1
				break

	for path, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True):
		if os.path.exists(path):
			return path
	return FONT_PATH
