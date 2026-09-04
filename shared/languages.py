class UnknownLanguageError(Exception):
	pass


MAX_LANGUAGE_INPUT_LEN = 40

LANGUAGE_NAMES: dict[str, str] = {
	"aa": "Afar",
	"ab": "Abkhazian",
	"af": "Afrikaans",
	"ak": "Akan",
	"am": "Amharic",
	"an": "Aragonese",
	"ar": "Arabic",
	"as": "Assamese",
	"av": "Avaric",
	"ay": "Aymara",
	"az": "Azerbaijani",
	"ba": "Bashkir",
	"be": "Belarusian",
	"bg": "Bulgarian",
	"bi": "Bislama",
	"bm": "Bambara",
	"bn": "Bengali",
	"bo": "Tibetan",
	"br": "Breton",
	"bs": "Bosnian",
	"ca": "Catalan",
	"ce": "Chechen",
	"ch": "Chamorro",
	"co": "Corsican",
	"cr": "Cree",
	"cs": "Czech",
	"cv": "Chuvash",
	"cy": "Welsh",
	"da": "Danish",
	"de": "German",
	"dv": "Divehi",
	"dz": "Dzongkha",
	"ee": "Ewe",
	"el": "Greek",
	"en": "English",
	"eo": "Esperanto",
	"es": "Spanish",
	"et": "Estonian",
	"eu": "Basque",
	"fa": "Persian",
	"ff": "Fulah",
	"fi": "Finnish",
	"fj": "Fijian",
	"fo": "Faroese",
	"fr": "French",
	"fy": "Western Frisian",
	"ga": "Irish",
	"gd": "Scottish Gaelic",
	"gl": "Galician",
	"gn": "Guarani",
	"gu": "Gujarati",
	"gv": "Manx",
	"ha": "Hausa",
	"he": "Hebrew",
	"hi": "Hindi",
	"hr": "Croatian",
	"ht": "Haitian Creole",
	"hu": "Hungarian",
	"hy": "Armenian",
	"ia": "Interlingua",
	"id": "Indonesian",
	"ig": "Igbo",
	"is": "Icelandic",
	"it": "Italian",
	"iu": "Inuktitut",
	"ja": "Japanese",
	"jv": "Javanese",
	"ka": "Georgian",
	"kg": "Kongo",
	"ki": "Kikuyu",
	"kk": "Kazakh",
	"kl": "Greenlandic",
	"km": "Khmer",
	"kn": "Kannada",
	"ko": "Korean",
	"ks": "Kashmiri",
	"ku": "Kurdish",
	"kv": "Komi",
	"kw": "Cornish",
	"ky": "Kyrgyz",
	"la": "Latin",
	"lb": "Luxembourgish",
	"lg": "Ganda",
	"li": "Limburgish",
	"ln": "Lingala",
	"lo": "Lao",
	"lt": "Lithuanian",
	"lu": "Luba-Katanga",
	"lv": "Latvian",
	"mg": "Malagasy",
	"mh": "Marshallese",
	"mi": "Maori",
	"mk": "Macedonian",
	"ml": "Malayalam",
	"mn": "Mongolian",
	"mr": "Marathi",
	"ms": "Malay",
	"mt": "Maltese",
	"my": "Burmese",
	"na": "Nauruan",
	"nb": "Norwegian Bokmal",
	"nd": "North Ndebele",
	"ne": "Nepali",
	"nl": "Dutch",
	"nn": "Norwegian Nynorsk",
	"no": "Norwegian",
	"nr": "South Ndebele",
	"nv": "Navajo",
	"ny": "Chichewa",
	"oc": "Occitan",
	"oj": "Ojibwe",
	"om": "Oromo",
	"or": "Odia",
	"os": "Ossetian",
	"pa": "Punjabi",
	"pl": "Polish",
	"ps": "Pashto",
	"pt": "Portuguese",
	"qu": "Quechua",
	"rm": "Romansh",
	"rn": "Rundi",
	"ro": "Romanian",
	"ru": "Russian",
	"rw": "Kinyarwanda",
	"sa": "Sanskrit",
	"sc": "Sardinian",
	"sd": "Sindhi",
	"se": "Northern Sami",
	"sg": "Sango",
	"si": "Sinhala",
	"sk": "Slovak",
	"sl": "Slovenian",
	"sm": "Samoan",
	"sn": "Shona",
	"so": "Somali",
	"sq": "Albanian",
	"sr": "Serbian",
	"ss": "Swati",
	"st": "Southern Sotho",
	"su": "Sundanese",
	"sv": "Swedish",
	"sw": "Swahili",
	"ta": "Tamil",
	"te": "Telugu",
	"tg": "Tajik",
	"th": "Thai",
	"ti": "Tigrinya",
	"tk": "Turkmen",
	"tl": "Tagalog",
	"tn": "Tswana",
	"to": "Tongan",
	"tr": "Turkish",
	"ts": "Tsonga",
	"tt": "Tatar",
	"tw": "Twi",
	"ty": "Tahitian",
	"ug": "Uyghur",
	"uk": "Ukrainian",
	"ur": "Urdu",
	"uz": "Uzbek",
	"ve": "Venda",
	"vi": "Vietnamese",
	"wa": "Walloon",
	"wo": "Wolof",
	"xh": "Xhosa",
	"yi": "Yiddish",
	"yo": "Yoruba",
	"za": "Zhuang",
	"zh": "Chinese",
	"zu": "Zulu",
}

EXTRA_ALIASES: dict[str, str] = {
	"bokmal": "nb",
	"brazilian": "pt",
	"brazilian portuguese": "pt",
	"cantonese": "zh",
	"castilian": "es",
	"chinese simplified": "zh",
	"chinese traditional": "zh",
	"dari": "fa",
	"farsi": "fa",
	"filipino": "tl",
	"flemish": "nl",
	"greenlandic": "kl",
	"hebrew ivrit": "he",
	"kirghiz": "ky",
	"kurmanji": "ku",
	"mandarin": "zh",
	"moldovan": "ro",
	"nynorsk": "nn",
	"oriya": "or",
	"panjabi": "pa",
	"persian farsi": "fa",
	"pilipino": "tl",
	"portuguese brazil": "pt",
	"simplified chinese": "zh",
	"sinhalese": "si",
	"sorani": "ku",
	"traditional chinese": "zh",
	"myanmar": "my",
	"burmese myanmar": "my",
	"greek modern": "el",
	"serbo croatian": "sr",
	"scots gaelic": "gd",
	"gaelic": "gd",
	"frisian": "fy",
	"sami": "se",
	"sotho": "st",
	"ndebele": "nd",
}

TRANSLATION_STYLES: frozenset[str] = frozenset(
	{
		"informal",
		"formal",
		"casual",
		"slang",
		"polite",
		"neutral",
		"friendly",
		"professional",
		"literary",
		"poetic",
		"technical",
		"archaic",
	}
)


def normalize_language_input(text: str) -> str:
	cleaned = " ".join(text.split()).strip().strip(".,;:!?\"'()[]").lower()
	return cleaned.replace("-", " ").replace("_", " ")


def build_lookup() -> dict[str, str]:
	lookup: dict[str, str] = {}
	for code, name in LANGUAGE_NAMES.items():
		lookup[code] = code
		lookup[normalize_language_input(name)] = code
	lookup.update(EXTRA_ALIASES)
	return lookup


LANGUAGE_LOOKUP: dict[str, str] = build_lookup()


def resolve_language_code(text: str | None) -> str | None:
	if not text or len(text) > MAX_LANGUAGE_INPUT_LEN:
		return None
	return LANGUAGE_LOOKUP.get(normalize_language_input(text))


def language_name(code: str | None) -> str | None:
	if not code:
		return None
	resolved = resolve_language_code(code)
	return LANGUAGE_NAMES[resolved] if resolved else None


def require_language_name(value: str | None) -> str:
	name = language_name(value)
	if name is None:
		raise UnknownLanguageError("That is not a language I recognise.")
	return name


def resolve_style(text: str | None) -> str | None:
	if not text:
		return None
	cleaned = normalize_language_input(text)
	return cleaned if cleaned in TRANSLATION_STYLES else None
