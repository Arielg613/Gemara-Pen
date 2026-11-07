#!/usr/bin/env python3
"""
Kitzur Yalkut Yosef for the scanner: word-group meanings, one file per chapter.

Source: Halacha on the Go's Yalkut Yosef data (~/hotg-work/data/yalkut/books),
the first five topics in book order (about 58,000 words, simanim 1–58).
Hebrew is used verbatim; English seif text is our existing AI translation.

Chapters are numbered 1..64 in book order ("ch01" …). Each part file
phrases/kyy/chNN.json is a list with one entry per seif, and each entry a list
of [n_words, "meaning"] chunks covering that seif's words in order. Meanings
are Claude's (labelled AI in the app), worded to fit our seif translation.

Usage:
  python3 kyy_tasks.py list                 chapters with word counts
  python3 kyy_tasks.py 5                    numbered Hebrew words + English for ch05
  python3 kyy_tasks.py --check phrases/kyy/ch05.json
"""
import html
import json
import os
import re
import sys

SRC = os.path.expanduser("~/hotg-work/data/yalkut/books")
N_TOPICS = 5
HEB_WORD = re.compile(r"[א-ת֑-ֽֿׁׂׄ-ׇ׳״'\"]+")


def words(he: str) -> list:
    return [t for t in HEB_WORD.findall(he) if re.search(r"[א-ת]", t)]


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def chapters() -> list:
    """[{key, label, titleHe, seifim: [[seif_label, he, en], ...]}] in book order."""
    lib = sorted(json.load(open(f"{SRC}/_library.json", encoding="utf-8")), key=lambda b: b["order"])[:N_TOPICS]
    out, last = [], ""
    for b in lib:
        for c in json.load(open(f"{SRC}/{b['slug']}.json", encoding="utf-8"))["chapters"]:
            if c.get("addendum"):
                label = f"after Siman {last}"
            else:
                last = c["n"]
                label = f"Siman {last}"
            seifim = []
            for s in c["sections"]:
                he = clean(" ".join(s.get("he") or []))
                if words(he):
                    seifim.append([s.get("n") or "", he, clean(" ".join(s.get("en") or []))])
            out.append({"key": f"ch{len(out) + 1:02d}", "label": label, "titleHe": clean(c.get("titleHe") or ""), "seifim": seifim})
    return out


def show(ch: dict) -> None:
    print(f"# {ch['key']} · {ch['label']} · {ch['titleHe']} · {len(ch['seifim'])} seifim\n")
    for i, (n, he, en) in enumerate(ch["seifim"]):
        ws = words(he)
        print(f"## seif index {i} (seif {n}, {len(ws)} words)")
        print(" ".join(f"{j}:{w}" for j, w in enumerate(ws)))
        print("EN:", en, "\n")


def check(path: str) -> None:
    key = os.path.basename(path)[:-5]
    ch = next((c for c in chapters() if c["key"] == key), None)
    if not ch:
        sys.exit(f"no chapter {key}")
    part, bad = json.load(open(path, encoding="utf-8")), []
    if len(part) != len(ch["seifim"]):
        bad.append(f"{len(part)} seif lists, chapter has {len(ch['seifim'])}")
    for i, (chunks, seif) in enumerate(zip(part, ch["seifim"])):
        want = len(words(seif[1]))
        if any(not (isinstance(c, list) and len(c) == 2 and isinstance(c[0], int) and c[0] > 0 and isinstance(c[1], str)) for c in chunks):
            bad.append(f"seif {i}: every chunk must be [n_words>0, \"meaning\"]")
            continue
        got = sum(c[0] for c in chunks)
        if got != want:
            bad.append(f"seif {i}: chunks cover {got} words, seif has {want}")
        for c in chunks:
            if not c[1].strip():
                bad.append(f"seif {i}: empty meaning (every word group needs English)")
            if c[0] > 6:
                bad.append(f"seif {i}: long group ({c[0]} words) = {c[1]}")
    print("\n".join(bad) if bad else f"OK {path}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--check":
        check(a[1])
    elif a and a[0] == "list":
        tot = 0
        for c in chapters():
            n = sum(len(words(s[1])) for s in c["seifim"])
            tot += n
            print(c["key"], c["label"], len(c["seifim"]), n, tot)
    elif a:
        show(chapters()[int(a[0]) - 1])
    else:
        print(__doc__)
