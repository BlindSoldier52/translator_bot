import re

MAX_PIECE_CHARS = 3000
MAX_BATCH_UNITS = 25
MAX_BATCH_CHARS = 3000

SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?…。！？])\s+")


def normalize_unit(unit: str) -> str:
	return " ".join(unit.split())


def split_units_for_translation(units: list[str]) -> tuple[list[str], list[int]]:
	pieces: list[str] = []
	owners: list[int] = []
	for index, unit in enumerate(units):
		for piece in split_one_unit(normalize_unit(unit)):
			pieces.append(piece)
			owners.append(index)
	return pieces, owners


def merge_translated_pieces(translated: list[str], owners: list[int], unit_count: int) -> list[str]:
	grouped: list[list[str]] = [[] for _ in range(unit_count)]
	for owner, piece in zip(owners, translated):
		grouped[owner].append(piece.strip())
	return [" ".join(part for part in parts if part) for parts in grouped]


def group_pieces_into_batches(pieces: list[str]) -> list[list[str]]:
	batches: list[list[str]] = []
	current: list[str] = []
	current_chars = 0
	for piece in pieces:
		too_many = len(current) >= MAX_BATCH_UNITS
		too_long = current_chars + len(piece) > MAX_BATCH_CHARS
		if current and (too_many or too_long):
			batches.append(current)
			current = []
			current_chars = 0
		current.append(piece)
		current_chars += len(piece)
	if current:
		batches.append(current)
	return batches


def split_one_unit(unit: str) -> list[str]:
	if not unit:
		return [""]
	if len(unit) <= MAX_PIECE_CHARS:
		return [unit]

	pieces: list[str] = []
	current = ""
	for sentence in SENTENCE_BOUNDARY_RE.split(unit):
		for fragment in split_oversized_sentence(sentence):
			if current and len(current) + 1 + len(fragment) > MAX_PIECE_CHARS:
				pieces.append(current)
				current = fragment
			else:
				current = f"{current} {fragment}" if current else fragment
	if current:
		pieces.append(current)
	return pieces


def split_oversized_sentence(sentence: str) -> list[str]:
	if len(sentence) <= MAX_PIECE_CHARS:
		return [sentence]

	fragments = []
	remaining = sentence
	while len(remaining) > MAX_PIECE_CHARS:
		cut = remaining.rfind(" ", 0, MAX_PIECE_CHARS)
		if cut <= 0:
			cut = MAX_PIECE_CHARS
		fragments.append(remaining[:cut].strip())
		remaining = remaining[cut:].strip()
	if remaining:
		fragments.append(remaining)
	return fragments
