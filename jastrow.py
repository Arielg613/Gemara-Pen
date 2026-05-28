import json
import os
import re

_index: dict | None = None
_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "jastrow.json")

# Common Aramaic/Hebrew prefixes and suffixes to strip when looking for a root.
# Order matters — try longer ones first to avoid partial stripping.
_PREFIXES = [
    "מת", "הת", "נת",        # hitpael-style
    "ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש", "א",
]
_SUFFIXES = [
    # Verb endings
    "תון", "תין", "נון", "נין",
    "ות", "ין", "ון", "תם", "תן", "נו", "תי", "תא",
    "ית", "ות", "את",
    # Noun / adjective endings
    "יות", "יין", "יהם", "יהן", "יכם", "יכן",
    "הון", "הין", "כון", "כין",
    "יה", "יו", "יך", "יי",
    "הם", "הן", "כם", "כן",
    "נא", "נו",
    # Aramaic definite state (alef at end)
    "א",
    # Feminine
    "ה", "ת",
    # Plural
    "ים", "ות",
    # Single-letter verb/noun suffixes
    "ן", "י", "ו",
]


def strip_nikud(text: str) -> str:
    return re.sub(r"[֑-ׇ]", "", text).strip()


def _load():
    global _index
    if _index is None:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _index = json.load(f)


def _exact(key: str) -> list:
    return _index.get(key, [])


def _candidates(word: str) -> list[str]:
    """Generate possible root forms by stripping prefixes and suffixes."""
    candidates = []

    # Strip suffixes first
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 2:
            stem = word[: -len(suf)]
            candidates.append(stem)
            # Also try stripping a prefix off the stem
            for pre in _PREFIXES:
                if stem.startswith(pre) and len(stem) - len(pre) >= 2:
                    candidates.append(stem[len(pre):])
            # Handle kal active participle: 2nd letter is ו as binyan marker
            # e.g. אוחז → אחז (alef-vav-chet-zayn → alef-chet-zayn)
            if len(stem) >= 3 and stem[1] == "ו":
                without_vav = stem[0] + stem[2:]
                candidates.append(without_vav)
                for pre in _PREFIXES:
                    if without_vav.startswith(pre) and len(without_vav) - len(pre) >= 2:
                        candidates.append(without_vav[len(pre):])

    # Strip prefixes alone
    for pre in _PREFIXES:
        if word.startswith(pre) and len(word) - len(pre) >= 2:
            stem = word[len(pre):]
            candidates.append(stem)

    # Also try each candidate with ה appended (many Aramaic/Hebrew nouns end in ה)
    with_heh = [c + "ה" for c in candidates if not c.endswith("ה")]
    candidates.extend(with_heh)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen and c != word:
            seen.add(c)
            unique.append(c)
    return unique


def lookup(word: str) -> list:
    """Look up a word in Jastrow, falling back to root-finding if not found directly."""
    _load()
    key = strip_nikud(word)

    # 1. Exact match
    result = _exact(key)
    if result:
        return result

    # 2. Try stripping prefixes/suffixes to find the root
    for candidate in _candidates(key):
        result = _exact(candidate)
        if result:
            return result

    # 3. Starts-with fallback (user typed partial root)
    matches = []
    for hw_key, entries in _index.items():
        if hw_key.startswith(key) and hw_key != key:
            matches.extend(entries)
        if len(matches) >= 5:
            break

    return matches
