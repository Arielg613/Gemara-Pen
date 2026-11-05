#!/usr/bin/env python3
"""
Build the data file for the offline scanner test app (docs/scan/).

Output: docs/scan/<tractate>.json
  {
    "tractate": "Berakhot",
    "en_source": "William Davidson Edition (Koren / Steinsaltz) via Sefaria",
    "segs":  [[daf, hebrew_with_nikud, english_html], ...],   # Gemara order
    "gloss": {daf: {normalized_word: gloss}}                  # from lookup/<tractate>.json
  }

Hebrew comes from Sefaria's GCS export (same source as build_dictionary.py).
English keeps only <b> tags. In the William Davidson edition, bold text is the
literal translation and plain text is the Steinsaltz explanation.

Usage: python build_scan_data.py Berakhot
"""
import json
import re
import sys
import urllib.parse
import urllib.request

SEDER = {
    "Berakhot": "Seder Zeraim",
    "Shabbat": "Seder Moed",
    "Megillah": "Seder Moed",
}


def fetch(tractate: str, lang: str) -> list:
    path = f"Talmud/Bavli/{SEDER[tractate]}/{tractate}/{lang}/merged.json"
    url = "https://storage.googleapis.com/sefaria-export/json/" + urllib.parse.quote(path)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)["text"]


def flatten(node) -> list:
    if isinstance(node, str):
        return [node]
    out = []
    for x in node or []:
        out.extend(flatten(x))
    return out


def clean_he(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def clean_en(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<(/?)strong>", r"<\1b>", s)
    s = re.sub(r"<(?!/?b>)[^>]+>", "", s)   # keep only <b> / </b>
    return re.sub(r"\s+", " ", s).strip()


def daf_label(idx: int) -> str:
    return f"{(idx - 2) // 2 + 2}{'a' if (idx - 2) % 2 == 0 else 'b'}"


def main():
    tractate = sys.argv[1] if len(sys.argv) > 1 else "Berakhot"
    he, en = fetch(tractate, "Hebrew"), fetch(tractate, "English")
    segs = []
    for idx in range(2, len(he)):
        hs, es = flatten(he[idx]), flatten(en[idx] if idx < len(en) else [])
        for i, h in enumerate(hs):
            h = clean_he(h)
            if h:
                segs.append([daf_label(idx), h, clean_en(es[i]) if i < len(es) else ""])
    gloss = json.load(open(f"lookup/{tractate}.json", encoding="utf-8"))["dafs"]
    out = {
        "tractate": tractate,
        "en_source": "William Davidson Edition (Koren / Steinsaltz) via Sefaria",
        "segs": segs,
        "gloss": gloss,
    }
    path = f"docs/scan/{tractate}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{path}: {len(segs)} segments, {len(gloss)} dafs")


if __name__ == "__main__":
    main()
