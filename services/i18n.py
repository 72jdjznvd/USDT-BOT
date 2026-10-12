import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALES_DIR = BASE_DIR / "locales"

SUPPORTED_LANGUAGES = ("az", "ru")
DEFAULT_LANGUAGE = "az"

_TRANSLATIONS = {}


def load_translations():
    """Azərbaycan və rus dili tərcümələrini yükləyir."""
    global _TRANSLATIONS

    translations = {}

    for language in SUPPORTED_LANGUAGES:
        file_path = LOCALES_DIR / f"{language}.json"

        if not file_path.is_file():
            raise FileNotFoundError(
                f"Tərcümə faylı tapılmadı: {file_path}"
            )

        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(
                f"Tərcümə faylının formatı yanlışdır: {file_path}"
            )

        translations[language] = data

    _TRANSLATIONS = translations


def get_text(language: str, key: str, **kwargs) -> str:
    """Seçilmiş dildə mətn qaytarır."""
    if not _TRANSLATIONS:
        load_translations()

    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    text = _TRANSLATIONS.get(language, {}).get(key)

    if text is None:
        text = _TRANSLATIONS.get(DEFAULT_LANGUAGE, {}).get(key)

    if text is None:
        return key

    try:
        return text.format(**kwargs)
    except (KeyError, ValueError):
        return text
