"""
rebuild_ordered.py

Rebuilds real_dictionary.json organized by daf, words in the order
they first appear in the Gemara text.

Output format:
{
  "tractate": "Megillah",
  "dafs": {
    "2a": [
      {"word": "מְגִילָּה", "translation": "scroll", "root": "מגל"},
      ...
    ],
    "2b": [...],
    ...
  }
}

Words that appear in multiple dafs are included in each daf they appear in.
Within a daf, each word appears only once (first occurrence).
"""

import json
import re
import sys
from urllib.parse import quote

import requests

GCS_BASE = "https://storage.googleapis.com/sefaria-export/json/Talmud/Bavli"
TRACTATES_SEDER = {
    "Megillah": "Seder Moed",
}


def strip_nikud(text):
    return re.sub(r'[֑-ׇ]', '', text)


def strip_html(text):
    return re.sub(r'<[^>]+>', '', text).strip()


def flatten(node):
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        out = []
        for item in node:
            out.extend(flatten(item))
        return out
    return []


def split_words(text):
    clean = re.sub(r'<[^>]+>', '', text)
    parts = re.split(r'[\s־׀׃׆׳״–—",;:()\[\]\'\.!\?/\-]+', clean)
    return [p for p in parts if p and re.search(r'[א-ת]', p)]


def daf_label(idx):
    n = (idx - 2) // 2 + 2
    side = 'a' if (idx - 2) % 2 == 0 else 'b'
    return f"{n}{side}"


def extract_root(word):
    PREFIXES = ['ו', 'ה', 'ב', 'ל', 'מ', 'כ', 'ד', 'ש']
    bare = strip_nikud(word).strip()
    for _ in range(3):
        for pfx in PREFIXES:
            if bare.startswith(pfx) and len(bare) - len(pfx) >= 3:
                bare = bare[len(pfx):]
                break
        else:
            break
    return bare


def build(tractate):
    seder = "Seder Moed"  # default; add lookup if needed

    # Load existing translation table (flat: word → translation)
    print("Loading existing translations…")
    with open("real_dictionary.json", encoding="utf-8") as f:
        existing = json.load(f)

    # Build a normalized lookup: bare_consonants → translation
    # (handles nikud variants — maps to first matching translation found)
    bare_to_trans = {}
    bare_to_root  = {}
    for word, node in existing.items():
        bare = strip_nikud(word)
        if bare not in bare_to_trans:
            # Extract translation from either old flat format or new entries[] format
            if isinstance(node, dict):
                if 'translation' in node:
                    bare_to_trans[bare] = node['translation']
                    bare_to_root[bare]  = node.get('root', extract_root(word))
                elif 'entries' in node and node['entries']:
                    bare_to_trans[bare] = node['entries'][0]['translation']
                    bare_to_root[bare]  = node.get('root', extract_root(word))

    print(f"  Translation table: {len(bare_to_trans)} entries")

    # Download text
    heb_url = f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/Hebrew/merged.json"
    eng_url = f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/English/merged.json"
    print(f"Downloading {tractate}…")
    heb_list = requests.get(heb_url, timeout=60).json()["text"]
    eng_list = requests.get(eng_url, timeout=60).json()["text"]
    print(f"  {len(heb_list)-2} amudim")

    dafs = {}

    for idx in range(2, len(heb_list)):
        daf = daf_label(idx)
        heb_segs = flatten(heb_list[idx])
        seen_this_daf = set()
        daf_words = []

        for seg in heb_segs:
            seg = strip_html(seg)
            for word in split_words(seg):
                bare = strip_nikud(word)
                if bare in seen_this_daf:
                    continue
                seen_this_daf.add(bare)

                translation = bare_to_trans.get(bare, '')
                root = bare_to_root.get(bare, extract_root(word))

                if translation:
                    daf_words.append({
                        "word":        word,
                        "translation": translation,
                        "root":        root,
                    })

        dafs[daf] = daf_words

    # Stats
    total_entries = sum(len(v) for v in dafs.values())
    print(f"\nDafs: {len(dafs)}  |  Total word entries: {total_entries}")
    for daf, words in list(dafs.items())[:4]:
        print(f"  {daf}: {len(words)} words  — first 3: {[w['word'] for w in words[:3]]}")

    result = {"tractate": tractate, "dafs": dafs}

    with open("real_dictionary.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\nSaved → real_dictionary.json")
    return result


if __name__ == "__main__":
    tractate = sys.argv[1] if len(sys.argv) > 1 else "Megillah"
    build(tractate)
