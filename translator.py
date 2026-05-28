import re
from urllib.parse import quote

import requests

GCS_BASE = "https://storage.googleapis.com/sefaria-export/json/Talmud/Bavli"

TRACTATES = {
    "Berakhot":      {"seder": "Seder Zeraim",  "max_daf": 64},
    "Shabbat":       {"seder": "Seder Moed",    "max_daf": 157},
    "Eruvin":        {"seder": "Seder Moed",    "max_daf": 105},
    "Pesachim":      {"seder": "Seder Moed",    "max_daf": 121},
    "Yoma":          {"seder": "Seder Moed",    "max_daf": 88},
    "Sukkah":        {"seder": "Seder Moed",    "max_daf": 56},
    "Beitzah":       {"seder": "Seder Moed",    "max_daf": 40},
    "Rosh Hashanah": {"seder": "Seder Moed",    "max_daf": 35},
    "Taanit":        {"seder": "Seder Moed",    "max_daf": 31},
    "Megillah":      {"seder": "Seder Moed",    "max_daf": 32},
    "Moed Katan":    {"seder": "Seder Moed",    "max_daf": 29},
    "Chagigah":      {"seder": "Seder Moed",    "max_daf": 27},
    "Yevamot":       {"seder": "Seder Nashim",  "max_daf": 122},
    "Ketubot":       {"seder": "Seder Nashim",  "max_daf": 112},
    "Nedarim":       {"seder": "Seder Nashim",  "max_daf": 91},
    "Nazir":         {"seder": "Seder Nashim",  "max_daf": 66},
    "Sotah":         {"seder": "Seder Nashim",  "max_daf": 49},
    "Gittin":        {"seder": "Seder Nashim",  "max_daf": 90},
    "Kiddushin":     {"seder": "Seder Nashim",  "max_daf": 82},
    "Bava Kamma":    {"seder": "Seder Nezikin", "max_daf": 119},
    "Bava Metzia":   {"seder": "Seder Nezikin", "max_daf": 119},
    "Bava Batra":    {"seder": "Seder Nezikin", "max_daf": 176},
    "Sanhedrin":     {"seder": "Seder Nezikin", "max_daf": 113},
    "Makkot":        {"seder": "Seder Nezikin", "max_daf": 24},
    "Shevuot":       {"seder": "Seder Nezikin", "max_daf": 49},
    "Avodah Zarah":  {"seder": "Seder Nezikin",  "max_daf": 76},
    "Horayot":       {"seder": "Seder Nezikin",  "max_daf": 14},
    "Zevachim":      {"seder": "Seder Kodashim", "max_daf": 120},
    "Menachot":      {"seder": "Seder Kodashim", "max_daf": 110},
    "Chullin":       {"seder": "Seder Kodashim", "max_daf": 142},
    "Bekhorot":      {"seder": "Seder Kodashim", "max_daf": 61},
    "Arakhin":       {"seder": "Seder Kodashim", "max_daf": 34},
    "Temurah":       {"seder": "Seder Kodashim", "max_daf": 34},
    "Keritot":       {"seder": "Seder Kodashim", "max_daf": 28},
    "Meilah":        {"seder": "Seder Kodashim", "max_daf": 22},
    "Tamid":         {"seder": "Seder Kodashim", "max_daf": 33},
    "Niddah":        {"seder": "Seder Taharot",  "max_daf": 73},
}

# In-memory cache so we only download each tractate once per session
_cache: dict = {}


def _gcs_url(tractate: str, language: str) -> str:
    seder = TRACTATES[tractate]["seder"]
    return f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/{quote(language)}/merged.json"


def _load_tractate(tractate: str) -> dict:
    if tractate in _cache:
        return _cache[tractate]

    heb_url = _gcs_url(tractate, "Hebrew")
    eng_url = _gcs_url(tractate, "English")

    heb = requests.get(heb_url, timeout=30)
    heb.raise_for_status()
    eng = requests.get(eng_url, timeout=30)
    eng.raise_for_status()

    _cache[tractate] = {
        "he": heb.json()["text"],
        "en": eng.json()["text"],
    }
    return _cache[tractate]


def strip_nikud(text: str) -> str:
    """Strip vowel points and cantillation marks so bare letters match pointed text."""
    return re.sub(r"[֑-ׇ]", "", text)


def search_word_in_tractate(word: str, tractate: str, max_results: int = 30) -> list:
    """Search for a word across all daf in a tractate."""
    data = _load_tractate(tractate)
    needle = strip_nikud(word)
    results = []

    heb_list = data["he"]
    eng_list = data["en"]

    for daf_idx in range(2, len(heb_list)):
        heb_daf = heb_list[daf_idx] or []
        eng_daf = eng_list[daf_idx] if daf_idx < len(eng_list) else []
        for i, heb in enumerate(heb_daf):
            if isinstance(heb, str) and needle in strip_nikud(heb):
                eng = eng_daf[i] if i < len(eng_daf) and isinstance(eng_daf[i], str) else ""
                results.append({
                    "daf": daf_idx,
                    "segment": i + 1,
                    "aramaic": heb,
                    "english": eng,
                })
                if len(results) >= max_results:
                    return results
    return results


def search_word_in_all_tractates(word: str, max_per_tractate: int = 5, max_total: int = 60) -> list:
    """Search every tractate and return up to max_total combined results."""
    results = []
    for tractate in sorted(TRACTATES.keys()):
        if len(results) >= max_total:
            break
        try:
            matches = search_word_in_tractate(word, tractate, max_results=max_per_tractate)
            for m in matches:
                m["tractate"] = tractate
                results.append(m)
        except Exception:
            continue
    return results


def search_word_in_daf(word: str, tractate: str, daf: str, amud: str = "a") -> list:
    """Return all segments of a daf that contain the search word.

    The GCS data stores each daf as a unit (both a and b sides combined),
    so amud is accepted for API compatibility but the full daf is always searched.
    """
    data = _load_tractate(tractate)
    daf_idx = int(daf)

    heb_list = data["he"]
    eng_list = data["en"]

    if daf_idx >= len(heb_list):
        return []

    heb_daf = heb_list[daf_idx] or []
    eng_daf = eng_list[daf_idx] if daf_idx < len(eng_list) else []

    needle = strip_nikud(word)
    results = []

    for i, heb in enumerate(heb_daf):
        if isinstance(heb, str) and needle in strip_nikud(heb):
            eng = eng_daf[i] if i < len(eng_daf) and isinstance(eng_daf[i], str) else ""
            results.append({
                "segment": i + 1,
                "aramaic": heb,
                "english": eng,
            })

    return results
