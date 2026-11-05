#!/usr/bin/env python3
"""
Build docs/scan/jastrow.json — a compact, Berakhot-only slice of Jastrow for
the offline scanner (docs/scan/jastrow.js does the lookups in the browser).

Usage:
  python3 build_jastrow_data.py                 # reads jastrow.json from git 09baf13
  python3 build_jastrow_data.py path/to/jastrow.json

The full dictionary (28k headwords, ~10MB) and the original Python lookup
engine (jastrow.py) live only in git history at commit 09baf13. We exec that
jastrow.py to reuse its distill() gloss extractor, cross-ref regex and the
_QUICK_GLOSSES table, and we mirror its prefix/suffix candidate generation
here (with cost tracking). docs/scan/jastrow.js implements the SAME candidate
generation + ranking — keep the two in sync if you change either.

Output format (arrays keep the file small):
  {
    "v": 1,
    "e": { key: [ [head, gloss, def, xref?], ... ], ... },   # key = consonants only
    "q": { key: quick_gloss, ... }                           # hand-written overrides
  }
  gloss = distilled one-line meaning (may be ""), or an INT n meaning def[:n],
  def = cleaned text <= ~DEF_MAX chars ("" on cross-ref rows),
  xref  = key of the entry this one points to ("v. X"), present only if it exists.
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_COMMIT = "09baf13"
BERAKHOT = os.path.join(ROOT, "docs", "scan", "Berakhot.json")
OUT = os.path.join(ROOT, "docs", "scan", "jastrow.json")
DEF_MAX = 200
MAX_RESULTS = 3


def git_show(path):
    return subprocess.run(["git", "-C", ROOT, "show", f"{SRC_COMMIT}:{path}"],
                          check=True, capture_output=True).stdout.decode("utf-8")


# ── Reuse helpers from the original jastrow.py ──────────────────────────────
_J = {"__name__": "jastrow_09baf13", "__file__": os.path.join(ROOT, "jastrow.py")}
exec(compile("from __future__ import annotations\n" + git_show("jastrow.py"),
             "jastrow.py@09baf13", "exec"), _J)
distill = _J["distill"]
XREF_RE = _J["_XREF_RE"]
LEAD_RE = _J["_LEAD_RE"]
CITATION_RE = _J["_CITATION_RE"]
QUICK = _J["_QUICK_GLOSSES"]

# ── Normalisation ───────────────────────────────────────────────────────────
TO_FINAL = {"מ": "ם", "נ": "ן", "פ": "ף", "כ": "ך", "צ": "ץ"}
FROM_FINAL = {v: k for k, v in TO_FINAL.items()}
NON_LETTER = re.compile(r"[^א-ת]")


def norm(word):
    """Consonants only; interior final letters made regular, last letter final."""
    w = NON_LETTER.sub("", word)
    if not w:
        return ""
    w = "".join(FROM_FINAL.get(c, c) for c in w[:-1]) + w[-1]
    return finalize(w)


def finalize(stem):
    if stem and stem[-1] in TO_FINAL:
        return stem[:-1] + TO_FINAL[stem[-1]]
    return stem


def split_words(text):
    # maqaf (U+05BE) joins words; treat it as a space, like any punctuation
    return [w for w in re.split(r"[\s־]+", text) if w]


# ── Candidate generation (mirror of jastrow.py _candidates, with costs) ─────
# Same lists as jastrow.py. PREP prefixes are "real" prepositions/conjunctions
# and cost 1 per letter; verb person-markers / binyan prefixes cost +0.5 extra.
PREFIXES = ["אית", "את", "מת", "הת", "נת",
            "ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
            "א", "י", "נ", "ת", "ק", "תי"]
SUFFIXES = ["ייתא",
            "תון", "תין", "נון", "נין",
            "יות", "יין", "יהם", "יהן", "יכם", "יכן",
            "הון", "הין", "כון", "כין",
            "תם", "תן",
            "תו", "תה", "תך",
            "יה", "יו", "יך", "יי",
            "הם", "הן", "כם", "כן",
            "נא", "נו", "תי",
            "ות", "ין", "ון", "ית",
            "תא", "את",
            "ים", "יא", "נן",
            "א", "ה", "ת", "ן", "י", "ו", "ך"]
SAFE_PREFIXES = ["ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
                 "א", "י", "נ", "ת", "ק",
                 "אית", "את", "מת", "הת", "נת"]
PREP = set("ובלכמהדש")
GROUP_ORDER = {"suf": 0, "pre": 1, "ext": 2}


def prefix_cost(p):
    return float(len(p)) if all(c in PREP for c in p) else len(p) + 0.5


def suffix_cost(s):
    return len(s) + (0.5 if len(s) == 1 else 0.0)


VAV_COST = 0.5
EXT_COST = 1.5


def candidates(word):
    """Return [(cand, cost, group, ops)] sorted best-first (exact NOT included).

    ops: list of (kind, text) with kind in p (prefix), s (suffix), v (vav), x (ext).
    """
    best = {}  # cand -> (cost, group_rank, ops)

    def add(stem, group, ops):
        if len(stem) < 2:
            return
        cost = sum(c for _, _, c in ops)
        o = [(k, t) for k, t, _ in ops]
        for c in (stem, finalize(stem)):
            if c == word:
                continue
            key = (cost, GROUP_ORDER[group])
            if c not in best or key < best[c][:2]:
                best[c] = (cost, GROUP_ORDER[group], o, group)

    # bases: original + vav-stripped variants
    bases = [(word, [])]
    if len(word) >= 3 and word[1] == "ו":
        f = word[0] + word[2:]
        bases.append((f, [("v", "ו", VAV_COST)]))
    if word.startswith("ו") and len(word) >= 4:
        inner = word[1:]
        bases.append((inner, [("p", "ו", 1.0)]))
        if len(inner) >= 3 and inner[1] == "ו":
            bases.append((inner[0] + inner[2:], [("p", "ו", 1.0), ("v", "ו", VAV_COST)]))
    for b, bops in bases[1:]:
        add(b, "pre", bops)

    first = []  # (stem, group, ops) from first-level stripping
    for base, bops in bases:
        for sfx in SUFFIXES:
            if base.endswith(sfx) and len(base) - len(sfx) >= 2:
                stem = base[:-len(sfx)]
                sops = bops + [("s", sfx, suffix_cost(sfx))]
                first.append((stem, "suf", sops))
                for pfx in PREFIXES:
                    if stem.startswith(pfx) and len(stem) - len(pfx) >= 2:
                        first.append((stem[len(pfx):], "suf", sops + [("p", pfx, prefix_cost(pfx))]))
                if len(stem) >= 3 and stem[1] == "ו":
                    wv = stem[0] + stem[2:]
                    vops = sops + [("v", "ו", VAV_COST)]
                    first.append((wv, "suf", vops))
                    for pfx in PREFIXES:
                        if wv.startswith(pfx) and len(wv) - len(pfx) >= 2:
                            first.append((wv[len(pfx):], "suf", vops + [("p", pfx, prefix_cost(pfx))]))
                if len(stem) >= 4:
                    for vpos in (2, 3):
                        if vpos < len(stem) and stem[vpos] == "ו":
                            nv = stem[:vpos] + stem[vpos + 1:]
                            vops = sops + [("v", "ו", VAV_COST)]
                            first.append((nv, "suf", vops))
                            for pfx in PREFIXES:
                                if nv.startswith(pfx) and len(nv) - len(pfx) >= 2:
                                    first.append((nv[len(pfx):], "suf", vops + [("p", pfx, prefix_cost(pfx))]))
        for pfx in PREFIXES:
            if base.startswith(pfx) and len(base) - len(pfx) >= 2:
                st = base[len(pfx):]
                pops = bops + [("p", pfx, prefix_cost(pfx))]
                first.append((st, "pre", pops))
                if len(st) >= 3 and st[1] == "ו":
                    first.append((st[0] + st[2:], "pre", pops + [("v", "ו", VAV_COST)]))

    for stem, group, ops in first:
        add(stem, group, ops)
    # second-level prefix stripping (e.g. ד + ב, ו + ל ...)
    for stem, group, ops in list(first) + [(b, "pre", o) for b, o in bases[1:]]:
        for pfx in SAFE_PREFIXES:
            if stem.startswith(pfx) and len(stem) - len(pfx) >= 2:
                add(stem[len(pfx):], "pre", ops + [("p", pfx, prefix_cost(pfx))])
    # synthetic ה / א extensions (stem + ה/א), last resort
    for c, (cost, g, o, group) in list(best.items()):
        for sfx in ("ה", "א"):
            if not c.endswith(sfx):
                x = (c[:-1] + FROM_FINAL[c[-1]] if c[-1] in FROM_FINAL else c) + sfx
                if x != word and x not in best:
                    best[x] = (cost + EXT_COST, GROUP_ORDER["ext"], o + [("x", sfx)], "ext")

    out = [(c, v[0], v[3], v[2]) for c, v in best.items()]
    out.sort(key=lambda t: (t[1], GROUP_ORDER[t[2]], -len(t[0]), t[0]))
    return out


# ── Definition cleaning ─────────────────────────────────────────────────────
TAG_RE = re.compile(r"<[^>]+>")


def clean_def(raw):
    s = TAG_RE.sub("", raw).strip()
    s = LEAD_RE.sub("", s).strip()
    s = re.sub(r"\s+", " ", s)
    # Talmud/Targum citations add little on a phone screen: cut at the first
    # one, unless that would leave almost nothing.
    m = CITATION_RE.search(s, 40)
    if m:
        s = s[:m.start()].rstrip(" ,;:—") + " …"
    if len(s) > DEF_MAX:
        cut = s[:DEF_MAX].rfind(" ")
        s = (s[:cut] if cut > DEF_MAX * 0.6 else s[:DEF_MAX]).rstrip(" ,;") + "…"
    return s


ANY_XREF_RE = re.compile(r"\bv\.\s+([\u05D0-\u05EA\u0591-\u05C7]+)")
NOT_GLOSS = {"top", "bot", "sub", "end", "beg", "preced", "foreg", "read", "note", "ed", "var"}
JUNK_GLOSS_RE = re.compile(r"^(\d\)\s*)?(as\s+|same\s+as\s+)?(preced|foreg)|^(pr\.\s*n|Part|Pl)\b")


def has_english(s):
    return any(w.lower() not in NOT_GLOSS for w in re.findall(r"\b[a-z]{3,}\b", s))


def good_gloss(g):
    g = g.strip()
    return g if len(g) >= 3 and has_english(g) and not JUNK_GLOSS_RE.search(g) else ""


def analyse_def(raw, index):
    """Return (gloss, xref_key_or_None) for one Jastrow definition.

    An entry is a cross-ref only when it is *just* a pointer ("v. X", "I, v. X",
    "Y. Ned. III, 38a top, v. X"); entries like ", v. X; cmp. Y) officer, esp.
    priest" keep their own meaning.
    """
    s = TAG_RE.sub("", raw).strip()
    m = XREF_RE.match(s)
    target_text = None
    if m:
        rest = s[m.end():]
        if not has_english(rest[:120]):
            target_text = m.group(1)
        else:  # real meaning after the pointer
            rest = re.sub(r"^[\s;,)]*(cmp\.[^)]*\)|b\.\s*h\.[^)]*\))?", "", rest)
            return good_gloss(distill(rest)), None
    elif len(s) < 70 and not has_english(ANY_XREF_RE.sub("", s)):
        mm = ANY_XREF_RE.search(s)
        if mm:
            target_text = mm.group(1)
    if target_text is not None:
        for t in target_text.split(","):
            k = norm(t.strip("., "))
            if len(k) >= 2 and k in index:
                return "", k
        return "", None
    return good_gloss(distill(s)), None


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = json.loads(git_show("data/jastrow.json"))

    # Normalise keys (some carry '*' etc.) and merge
    full = {}
    for k, entries in raw.items():
        nk = norm(k)
        if len(nk) >= 1:
            full.setdefault(nk, []).extend(entries)

    # Compact entries: [head, gloss, def, xref?]; content-bearing entries first
    index = {}
    for k, entries in full.items():
        rows = []
        for e in entries:
            d = e.get("def", "")
            g, x = analyse_def(d, full)
            cd = clean_def(d)
            rows.append([TAG_RE.sub("", e.get("hw", k)), g, cd] + ([x] if x else []))
        # stable sort: entries with a gloss, then cross-refs, then the rest
        rows.sort(key=lambda r: 1 if len(r) > 3 else (0 if r[1] else 2))
        index[k] = rows

    def resolve(word):
        """Exactly what jastrow.js lookup() does; returns used (key, idx) pairs.

        Pass 1 takes only entries with a real gloss (cross-refs count if the
        entry they point to has one), best candidate first; pass 2 fills any
        remaining slots with whatever else matched. A cross-ref contributes one
        entry: the first not-yet-shown entry of its target.
        """
        used, seen = [], set()
        cands = [word] + [c for c, _cost, _g, _ops in candidates(word)]
        cands = [c for c in cands if c in index]

        def sig(row):
            return (row[0], row[2] or row[1])

        for need_gloss in (True, False):
            for c in cands:
                for i, row in enumerate(index[c]):
                    if len(used) and sum(1 for u in used if u[2]) >= MAX_RESULTS:
                        return used
                    if len(row) > 3 and row[3] in index:
                        for j, tr in enumerate(index[row[3]]):
                            if sig(tr) in seen or len(tr) > 3:
                                continue
                            if need_gloss and not tr[1]:
                                break
                            seen.add(sig(tr))
                            used.append((c, i, False))
                            used.append((row[3], j, True))
                            break
                        continue
                    if len(row) > 3 or bool(row[1]) != need_gloss or sig(row) in seen:
                        continue
                    seen.add(sig(row))
                    used.append((c, i, True))
        return used

    with open(BERAKHOT, encoding="utf-8") as f:
        segs = json.load(f)["segs"]
    words = set()
    for seg in segs:
        for w in split_words(seg[1]):
            n = norm(w)
            if len(n) >= 2:
                words.add(n)

    keep = {}
    hit = 0
    for w in sorted(words):
        used = resolve(w)
        if used or w in QUICK:
            hit += 1
        for k, i, _shown in used:
            keep.setdefault(k, set()).add(i)

    def pack(row):
        head, g, d = row[0], row[1], row[2]
        if len(row) > 3:          # cross-ref: the target's text is shown instead
            return [head, "", "", row[3]]
        if g and d.startswith(g):  # gloss is a prefix of def: store its length
            g = len(g)
        return [head, g, d]

    e_out = {k: [pack(index[k][i]) for i in sorted(idx)] for k, idx in sorted(keep.items())}
    q_out = {}
    for k, v in QUICK.items():
        nk = " ".join(norm(p) for p in k.split())
        q_out[nk] = v
    out = {"v": 1, "src": "Jastrow, Dictionary of the Targumim (1903); Berakhot subset",
           "e": e_out, "q": q_out}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(OUT)
    n_rows = sum(len(v) for v in e_out.values())
    print(f"Jastrow headwords (normalised): {len(full):,}")
    print(f"Unique Berakhot words:          {len(words):,}")
    print(f"Words with >=1 hit:             {hit:,} ({100.0 * hit / len(words):.1f}%)")
    print(f"Kept keys / entries:            {len(e_out):,} / {n_rows:,}  (+{len(q_out)} quick glosses)")
    print(f"Wrote {os.path.relpath(OUT, ROOT)}: {size:,} bytes ({size / 1048576:.2f} MB)")


if __name__ == "__main__":
    main()
