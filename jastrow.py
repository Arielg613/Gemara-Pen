import json
import os
import re

_index: dict | None = None
_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "jastrow.json")


def _load():
    global _index
    if _index is None:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _index = json.load(f)


def strip_nikud(text: str) -> str:
    return re.sub(r"[֑-ׇ]", "", text).strip()


def lookup(word: str) -> list:
    """Look up a word in Jastrow. Returns a list of matching entries."""
    _load()
    key = strip_nikud(word)

    # 1. Exact match
    if key in _index:
        return _index[key]

    # 2. Match where the headword starts with the search word
    #    (handles cases where user types a root and gets all derived forms)
    matches = []
    for hw_key, entries in _index.items():
        if hw_key.startswith(key) and hw_key != key:
            matches.extend(entries)
        if len(matches) >= 5:
            break

    return matches
