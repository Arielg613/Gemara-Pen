#!/usr/bin/env python3
"""
Gemara Pen — offline brain test console.

Prove the dictionary works with zero internet, zero Flask, zero dependencies.
Run this on any device that has Python 3 and the two brain files:
    jastrow.py  +  data/jastrow.json

Usage:
    python pen_test.py            # interactive REPL
    python pen_test.py שבת מלכא  # look up specific words and exit
"""

import sys
import os

# Allow running from any directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jastrow import analyze

LANG = {
    "hebrew":  "[Hebrew]",
    "aramaic": "[Aramaic]",
    "both":    "[Hebrew & Aramaic]",
    "unknown": "",
}
MATCH_NOTE = {
    "root":   "root form",
    "prefix": "partial match",
    "exact":  "",
    "none":   "",
}

# Max chars of definition shown on the "pen screen" (small display)
_DEF_LIMIT = 220


def _show(result: dict) -> None:
    word = result["normalized"] or result["query"]

    if not result["found"]:
        print(f"\n  ✗  {word}  — not found in Jastrow\n")
        return

    note = MATCH_NOTE.get(result["match_type"], "")
    print(f"\n  {'─' * 48}")
    print(f"  {word}   {('(' + note + ')') if note else ''}")

    m = result.get("morphology", {})
    if m and (m.get("prefix") or m.get("suffix")):
        pre  = m.get("prefix", "")
        root = m.get("root", word)
        suf  = m.get("suffix", "")
        parts = []
        if pre:  parts.append(f"prefix: {pre}")
        parts.append(f"root: {root}")
        if suf:  parts.append(f"suffix: {suf}")
        print(f"  └─ {' | '.join(parts)}")

    print(f"  {'─' * 48}")

    for i, entry in enumerate(result["entries"][:2]):
        lang = LANG.get(entry["lang"], "")
        hw   = entry["hw"]
        defn = entry["def"]
        if len(defn) > _DEF_LIMIT:
            # cut at last space before limit so we don't break mid-word
            cut = defn[:_DEF_LIMIT].rfind(" ")
            defn = defn[:cut] + " …"

        if i:
            print(f"  {'· ' * 24}")
        if lang:
            print(f"  {lang}")
        print(f"  {hw}")
        print(f"  {defn}")

    print(f"  {'─' * 48}\n")


def _batch(words: list) -> None:
    for w in words:
        _show(analyze(w))


def _repl() -> None:
    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║   Gemara Pen — Offline Brain     ║")
    print("  ║   Type a word.  'q' to quit.     ║")
    print("  ╚══════════════════════════════════╝")
    print()

    try:
        while True:
            try:
                word = input("  → ").strip()
            except EOFError:
                break
            if not word:
                continue
            if word.lower() in ("q", "quit", "exit"):
                break
            _show(analyze(word))
    except KeyboardInterrupt:
        pass

    print("\n  שלום!\n")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        _batch(args)
    else:
        _repl()
