#!/usr/bin/env python3
"""
Task sheets for writing phrase meanings (phrases/<Tractate>.json).

For each daf, prints every Sefaria segment with its words numbered (the same
words the scanner app counts) and Sefaria's bold = literal English.

Usage: python phrase_tasks.py Berakhot 2a 2b 3a
       python phrase_tasks.py Berakhot --check phrases/parts/Berakhot-2a.json
"""
import json
import re
import sys

NIKUD = re.compile(r"[֑-ׇ]")
HEB_WORD = re.compile(r"[א-ת֑-ֽֿׁׂׄ-ׇ׳״'\"]+")


def words(he: str) -> list:
    return [t for t in HEB_WORD.findall(he) if re.search(r"[א-ת]", t)]


def daf_segments(data: dict, daf: str) -> list:
    return [s for s in data["segs"] if s[0] == daf]


def sheet(data: dict, daf: str) -> str:
    out = [f"# {daf}"]
    for i, s in enumerate(daf_segments(data, daf)):
        ws = words(s[1])
        bold = " | ".join(re.sub(r"<[^>]+>", "", b) for b in re.findall(r"<b>(.*?)</b>", s[2]))
        plain = re.sub(r"<[^>]+>", "", s[2])
        out.append(f"## segment {i} ({len(ws)} words)")
        out.append(" ".join(f"{j}:{NIKUD.sub('', w)}" for j, w in enumerate(ws)))
        out.append("LITERAL: " + bold)
        out.append("FULL: " + plain)
        out.append("")
    return "\n".join(out)


def bold_runs(en: str) -> list:
    return [" ".join(re.sub(r"<[^>]+>", "", b).split()) for b in re.findall(r"<b>(.*?)</b>", en, re.S)]


def sefaria_only(en: str, chunks: list) -> list:
    """Every meaning must be copied exactly from Sefaria's bold English, in order, no overlap."""
    runs, r, pos, bad = bold_runs(en), 0, 0, []
    for c in chunks:
        m = c[1] if len(c) > 1 and isinstance(c[1], str) else ""
        if not m:
            continue
        found, r0, pos0 = False, r, pos
        while r < len(runs):
            for mt in re.finditer(re.escape(m), runs[r], re.I):
                a, b = mt.start(), mt.end()
                if a < pos:
                    continue
                if (a == 0 or not runs[r][a - 1].isalnum()) and (b == len(runs[r]) or not runs[r][b].isalnum()):
                    pos, found = b, True
                    break
            if found:
                break
            r, pos = r + 1, 0
        if not found:
            bad.append(f"not Sefaria's bold text (or out of order): {m!r}")
            r, pos = r0, pos0
    return bad


def check(data: dict, path: str) -> None:
    part = json.load(open(path, encoding="utf-8"))
    bad = []
    for daf, lists in part.items():
        segs = daf_segments(data, daf)
        if len(lists) != len(segs):
            bad.append(f"{daf}: {len(lists)} segment lists, text has {len(segs)}")
            continue
        for k, chunks in enumerate(lists):
            want = len(words(segs[k][1]))
            got = sum(c[0] for c in chunks)
            if want != got:
                bad.append(f"{daf} segment {k}: chunks cover {got} words, text has {want}")
            for c in chunks:
                if not (isinstance(c[0], int) and c[0] > 0 and isinstance(c[1], str)):
                    bad.append(f"{daf} segment {k}: bad chunk {c}")
            bad += [f"{daf} segment {k}: {m}" for m in sefaria_only(segs[k][2], chunks)]
    print("\n".join(bad) if bad else f"OK {path}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    tractate = sys.argv[1]
    data = json.load(open(f"docs/scan/{tractate}.json", encoding="utf-8"))
    if sys.argv[2] == "--check":
        check(data, sys.argv[3])
    else:
        print("\n\n".join(sheet(data, d) for d in sys.argv[2:]))
