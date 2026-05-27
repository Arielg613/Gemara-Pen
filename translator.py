import re
import requests

SEFARIA_BASE = "https://www.sefaria.org/api/texts"

TRACTATES = {
    "Berakhot": 64,
    "Shabbat": 157,
    "Eruvin": 105,
    "Pesachim": 121,
    "Yoma": 88,
    "Sukkah": 56,
    "Beitzah": 40,
    "Rosh Hashanah": 35,
    "Taanit": 31,
    "Megillah": 32,
    "Moed Katan": 29,
    "Chagigah": 27,
    "Yevamot": 122,
    "Ketubot": 112,
    "Nedarim": 91,
    "Nazir": 66,
    "Sotah": 49,
    "Gittin": 90,
    "Kiddushin": 82,
    "Bava Kamma": 119,
    "Bava Metzia": 119,
    "Bava Batra": 176,
    "Sanhedrin": 113,
    "Makkot": 24,
    "Shevuot": 49,
    "Avodah Zarah": 76,
    "Horayot": 14,
    "Niddah": 73,
}


def strip_nikud(text):
    """Remove vowel points and cantillation marks so bare letters match."""
    return re.sub(r"[֑-ׇ]", "", text)


def _flatten(lst):
    """Sefaria sometimes returns nested lists; flatten to a list of strings."""
    result = []
    for item in lst:
        if isinstance(item, list):
            result.extend(_flatten(item))
        elif isinstance(item, str):
            result.append(item)
    return result


def fetch_daf(tractate, daf, amud):
    ref = f"{tractate.replace(' ', '_')}.{daf}{amud}"
    url = f"{SEFARIA_BASE}/{ref}"
    resp = requests.get(url, params={"context": 0}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def search_word_in_daf(word, tractate, daf, amud):
    """Return all segments from a daf that contain the search word."""
    data = fetch_daf(tractate, daf, amud)

    aramaic_segments = _flatten(data.get("he", []))
    english_segments = _flatten(data.get("text", []))

    needle = strip_nikud(word)

    results = []
    for i, aram in enumerate(aramaic_segments):
        if needle in strip_nikud(aram):
            eng = english_segments[i] if i < len(english_segments) else ""
            results.append({
                "segment": i + 1,
                "aramaic": aram,
                "english": eng,
            })

    return results
