from __future__ import annotations

import json
from importlib.resources import files


LANGUAGES = {"zh_CN": "中文", "en": "English"}
_language = "zh_CN"
_translations: dict[str, str] = {}


def _load(language: str) -> dict[str, str]:
    resource = files(__package__).joinpath(f"{language}.json")
    with resource.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def set_language(language: str) -> None:
    global _language, _translations
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    _translations = _load(language)
    _language = language


def current_language() -> str:
    return _language


def tr(text: str, **values: object) -> str:
    translated = _translations.get(text, text)
    return translated.format(**values) if values else translated


set_language(_language)
