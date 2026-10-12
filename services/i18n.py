import json
from pathlib import Path

BASE_DIR = Path(file).resolve().parent.parent
LOCALES_DIR = BASE_DIR / "locales"

SUPPORTED_LANGUAGES = ("az", "ru")
DEFAULT_LANGUAGE = "az"

_TRANSLATIONS = {}

def load_translations():
"""Load Azerbaijani and Russian translations from JSON files."""
global _TRANSLATIONS

for language in SUPPORTED_LANGUAGES:
    file_path = LOCALES_DIR / f"{language}.json"

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Translation file not found: {file_path}"
        )

    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid translation file: {file_path}"
        )

    _TRANSLATIONS[language] = data

def get_text(language: str, key: str, **kwargs) -> str:
"""Return a translated text, with Azerbaijani fallback."""
if not _TRANSLATIONS:
load_translations()

language = (
    language if language in SUPPORTED_LANGUAGES
    else DEFAULT_LANGUAGE
)

text = _TRANSLATIONS.get(language, {}).get(key)

if text is None:
    text = _TRANSLATIONS.get(DEFAULT_LANGUAGE, {}).get(key)

if text is None:
    return key

try:
    return text.format(**kwargs)
except (KeyError, ValueError):
    return text
