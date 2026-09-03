import json
import os
from typing import Any


_translations_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'translations')
_current = {}
_current_lang = 'en'


def init(lang_code: str = 'en'):
    global _current, _current_lang
    _current_lang = lang_code
    path = os.path.join(_translations_dir, f'{lang_code}.json')
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Translation file not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        _current = json.load(f)


def t(key: str, **kwargs) -> str:
    template = _current.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def get_supported_languages():
    langs = []
    if os.path.exists(_translations_dir):
        for fname in os.listdir(_translations_dir):
            if fname.endswith('.json'):
                langs.append(fname.split('.')[0])
    return sorted(langs)
