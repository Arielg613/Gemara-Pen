"""
Gemara Pen — THE BRAIN (offline dictionary engine).

This module is fully self-contained and has NO network dependency. Given a
single Aramaic/Hebrew word, it returns Jastrow dictionary definitions plus a
detected language tag (Hebrew / Aramaic / both).

It is the part that runs ON the pen. To port it to the device you need only:
  1. This file (jastrow.py)
  2. The bundled dictionary data (data/jastrow.json)

Public API:
  analyze(word)  -> dict   full structured result (recommended for the pen)
  lookup(word)   -> list   just the matching entries (convenience)
  detect_language(entry) -> "hebrew" | "aramaic" | "both" | "unknown"
  strip_nikud(text) -> str  remove vowel points / cantillation

How a word is resolved (in order):
  1. exact   — the word is a headword as typed
  2. root    — strip Aramaic/Hebrew prefixes & suffixes to find the root
  3. prefix  — partial match (user typed the start of a root)
"""

import json
import os
import re

_index: dict | None = None
_cache: dict = {}   # normalized word → analyze() result (computed once per word)
_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "jastrow.json")

# Aramaic/Hebrew prefixes and suffixes to strip when looking for a root.
# Order matters — longer ones are tried first to avoid partial stripping.
_PREFIXES = [
    # Ithpeal/Ithpaal reflexive-passive binyan prefix (longer first)
    "אית", "את",
    # Hitpael-style (Hebrew borrowed patterns)
    "מת", "הת", "נת",
    # Single-letter prepositions, articles, conjunctions
    "ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
    # Single-letter imperfect person-markers and Afel alef
    "א", "י", "נ", "ת",
    # Aramaic present-tense marker קא and specific imperfect prefix תי
    "ק", "תי",
]
_SUFFIXES = [
    # 5-letter (longest first)
    "ייתא",  # Aramaic f. emphatic determinate (קמייתא → קמ)
    # 4-letter
    "תון", "תין", "נון", "נין",
    # 3-letter possessive/plural
    "יות", "יין", "יהם", "יהן", "יכם", "יכן",
    "הון", "הין", "כון", "כין",
    "תם", "תן",
    # 2-letter construct + possessive combos (e.g. שחיטתו → שחיט)
    "תו", "תה", "תך",
    # 2-letter verb / noun endings
    "יה", "יו", "יך", "יי",
    "הם", "הן", "כם", "כן",
    "נא", "נו", "תי",
    "ות", "ין", "ון", "ית",
    "תא", "את",
    "ים",
    "יא",   # Aramaic definite/emphatic plural (מלכיא "the kings")
    "נן",   # Aramaic 1st pl. perfect (חזינן → חזי)
    # 1-letter (last resort — most likely to overshoot)
    "א", "ה", "ת", "ן", "י", "ו", "ך",
]

# Matches Jastrow cross-reference definitions like ", v. רָקַק" or "v. רוֹק, רֵיק."
_XREF_RE = re.compile(r'^,?\s*v\.\s+([א-תְ-ׇ\s,\.]+)', re.UNICODE)

# Non-final → final letter map. After suffix stripping the terminal letter
# of a stem must be in final form to match dictionary headwords.
_TO_FINAL = {"מ": "ם", "נ": "ן", "פ": "ף", "כ": "ך", "צ": "ץ"}

# Prefixes allowed for SECOND-LEVEL stripping (applied after a first-level
# strip already yielded a candidate).  Suffix-stripped candidates have higher
# priority than prefix-only candidates in _resolve, so false positives from
# aggressive second-level stripping are naturally suppressed: the correct
# suffix-stripped root is always tried first.
_SAFE_PREFIXES = {
    "ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
    "א", "י", "נ", "ת", "ק",
    "אית", "את", "מת", "הת", "נת",
}


def strip_nikud(text: str) -> str:
    """Remove Hebrew vowel points and cantillation marks; trim whitespace."""
    return re.sub(r"[֑-ׇ]", "", text).strip()


def _finalize(stem: str) -> str:
    """Convert a stripped stem's last letter to its final form if applicable."""
    if stem and stem[-1] in _TO_FINAL:
        return stem[:-1] + _TO_FINAL[stem[-1]]
    return stem


def _load() -> None:
    global _index
    if _index is None:
        with open(_DATA_PATH, encoding="utf-8") as f:
            _index = json.load(f)


def _exact(key: str) -> list:
    return _index.get(key, [])


def detect_language(entry: dict) -> str:
    """Classify an entry as hebrew / aramaic / both / unknown.

    Uses Jastrow's own notation:
      (b. h.) / (Hebr.) -> Biblical/Hebrew origin
      Targ. / ch.       -> Targumic/Chaldee (Aramaic)
    """
    defn = entry.get("def", "")
    hw = entry.get("hw", "")
    is_hebrew = "(b. h.)" in defn or "(Hebr.)" in defn
    is_aramaic = (
        " ch." in defn or defn.startswith("ch.")
        or "Targ." in defn or "Targ." in hw
    )
    if is_hebrew and is_aramaic:
        return "both"
    if is_hebrew:
        return "hebrew"
    if is_aramaic:
        return "aramaic"
    return "unknown"


def _follow_xrefs(entries: list) -> list:
    """Replace pure cross-reference entries (", v. X") with what they point to."""
    result = []
    for entry in entries:
        m = _XREF_RE.match(entry.get("def", ""))
        if not m:
            result.append(entry)
            continue
        targets = [strip_nikud(t).strip("., ") for t in m.group(1).split(",")]
        followed = False
        for target in targets:
            if len(target) >= 2:
                ref = _exact(target)
                if ref:
                    result.extend(ref)
                    followed = True
                    break
        if not followed:
            result.append(entry)   # keep original if target not found
    return result


def _candidates(word: str) -> tuple[list[str], list[str], list[str]]:
    """Return (suf_forms, pre_forms, ext_forms).

    suf_forms  — candidates where at least one suffix was stripped.
                 These are tried first: suffix-stripped roots are more
                 specific and suppress false positives from pure prefix paths
                 (e.g. תנאים → תנא via suffix beats נאים via ת-prefix).
    pre_forms  — candidates from prefix-stripping only (no suffix removed),
                 including vav-removal, second-level strips.
    ext_forms  — synthetic ה/א extensions tried last.
    """
    suf: list[str] = []
    pre: list[str] = []

    def _add_suf(stem: str) -> None:
        suf.append(stem)
        f = _finalize(stem)
        if f != stem:
            suf.append(f)

    def _add_pre(stem: str) -> None:
        pre.append(stem)
        f = _finalize(stem)
        if f != stem:
            pre.append(f)

    # Expand word into base forms: original + vav-stripped variants.
    # Non-original forms are added directly as pre candidates.
    #   שוחט  → שחט  (ו at position 1, Kal pe-vav)
    #   ואומר → אומר → אמר  (ו-prefix then pe-vav root)
    #   ושוחט → שוחט → שחט
    bases: list[str] = [word]

    if len(word) >= 3 and word[1] == "ו":
        form = word[0] + word[2:]
        _add_pre(form)
        bases.append(form)

    if word.startswith("ו") and len(word) >= 4:
        inner = word[1:]
        _add_pre(inner)
        bases.append(inner)
        if len(inner) >= 3 and inner[1] == "ו":
            form2 = inner[0] + inner[2:]
            _add_pre(form2)
            bases.append(form2)

    for base in bases:
        # --- Suffix stripping (results go into suf) ---
        for sfx in _SUFFIXES:
            if base.endswith(sfx) and len(base) - len(sfx) >= 2:
                stem = base[: -len(sfx)]
                _add_suf(stem)
                for pfx in _PREFIXES:
                    if stem.startswith(pfx) and len(stem) - len(pfx) >= 2:
                        _add_suf(stem[len(pfx):])
                # Kal pe-vav: ו in position 1 of the suffix-stripped stem
                if len(stem) >= 3 and stem[1] == "ו":
                    wv = stem[0] + stem[2:]
                    _add_suf(wv)
                    for pfx in _PREFIXES:
                        if wv.startswith(pfx) and len(wv) - len(pfx) >= 2:
                            _add_suf(wv[len(pfx):])
                # Hollow-root ו from positions 2–3
                if len(stem) >= 4:
                    for vpos in (2, 3):
                        if vpos < len(stem) and stem[vpos] == "ו":
                            nv = stem[:vpos] + stem[vpos + 1:]
                            if len(nv) >= 2:
                                _add_suf(nv)
                                for pfx in _PREFIXES:
                                    if nv.startswith(pfx) and len(nv) - len(pfx) >= 2:
                                        _add_suf(nv[len(pfx):])

        # --- Prefix-only stripping (results go into pre) ---
        for pfx in _PREFIXES:
            if base.startswith(pfx) and len(base) - len(pfx) >= 2:
                stripped = base[len(pfx):]
                _add_pre(stripped)
                if len(stripped) >= 3 and stripped[1] == "ו":
                    _add_pre(stripped[0] + stripped[2:])

    # Deduplicate suf, then pre (excluding what suf already claimed)
    seen: set = set()
    unique_suf: list[str] = []
    for c in suf:
        if c not in seen and c != word:
            seen.add(c)
            unique_suf.append(c)

    unique_pre: list[str] = []
    for c in pre:
        if c not in seen and c != word:
            seen.add(c)
            unique_pre.append(c)

    # Second-level prefix stripping applied to both groups
    second_pre: list[str] = []
    for c in list(unique_suf) + list(unique_pre):
        for pfx in _SAFE_PREFIXES:
            if c.startswith(pfx) and len(c) - len(pfx) >= 2:
                c2 = c[len(pfx):]
                for cand in (c2, _finalize(c2)):
                    if cand not in seen and cand != word:
                        seen.add(cand)
                        second_pre.append(cand)
    unique_pre.extend(second_pre)

    # Synthetic extensions: ה / א tried last
    ext: list[str] = []
    ext_seen: set = seen.copy()
    for c in unique_suf + unique_pre:
        for sfx in ("ה", "א"):
            x = c + sfx
            if not c.endswith(sfx) and x not in ext_seen and x != word:
                ext_seen.add(x)
                ext.append(x)

    return unique_suf, unique_pre, ext


def _explain(original: str, root: str) -> dict:
    """Best-effort morpheme decomposition: what prefix/suffix was stripped?"""
    # Case 1: root is a simple substring of original
    idx = original.find(root)
    if idx >= 0:
        return {"prefix": original[:idx], "root": root, "suffix": original[idx + len(root):]}
    # Case 2: a ו was removed from the root (Kal participle / hollow root)
    for vpos in range(1, len(root)):
        expanded = root[:vpos] + "ו" + root[vpos:]
        idx = original.find(expanded)
        if idx >= 0:
            return {"prefix": original[:idx], "root": root, "suffix": original[idx + len(expanded):]}
    # Case 3: an aleph/heh extension was added — strip it for comparison
    if root and root[-1] in "האו":
        idx = original.find(root[:-1])
        if idx >= 0:
            return {"prefix": original[:idx], "root": root, "suffix": original[idx + len(root) - 1:]}
    return {"prefix": "", "root": root, "suffix": ""}


def _resolve(key: str) -> tuple[list, str, dict]:
    """Core search. Returns (entries, match_type, morphology)."""
    # 1. Exact match
    result = _follow_xrefs(_exact(key))
    if result:
        return result, "exact", {}

    # 2. Suffix-stripped candidates (higher priority) then prefix-only, then extensions.
    # Sorting each group by length descending: longer stripped stems are more specific.
    suf_forms, pre_forms, ext_forms = _candidates(key)
    for candidate in (sorted(suf_forms, key=len, reverse=True) +
                      sorted(pre_forms, key=len, reverse=True) +
                      ext_forms):
        result = _follow_xrefs(_exact(candidate))
        if result:
            return result, "root", _explain(key, candidate)

    # 3. Starts-with fallback (user typed a partial root)
    matches = []
    for hw_key, entries in _index.items():
        if hw_key.startswith(key) and hw_key != key:
            matches.extend(entries)
        if len(matches) >= 5:
            break
    matches = _follow_xrefs(matches)
    if matches:
        return matches, "prefix", {}

    return [], "none", {}


def analyze(word: str) -> dict:
    """Full structured lookup — the recommended entry point for the pen.

    Returns:
      {
        "query":      original input string,
        "normalized": nikud-stripped form actually searched,
        "found":      bool,
        "match_type": "exact" | "root" | "prefix" | "none",
        "morphology": {"prefix", "root", "suffix"} — only present for root matches,
        "entries":    [ {"hw", "def", "lang"}, ... ],
      }
    """
    _load()
    key = strip_nikud(word)

    if key in _cache:
        return _cache[key]

    entries, match_type, morphology = _resolve(key)
    tagged = [{**e, "lang": detect_language(e)} for e in entries]
    result = {
        "query": word,
        "normalized": key,
        "found": bool(tagged),
        "match_type": match_type,
        "entries": tagged,
    }
    if morphology:
        result["morphology"] = morphology
    _cache[key] = result
    return result


def lookup(word: str) -> list:
    """Convenience: return just the matching entries (each with a 'lang' tag)."""
    return analyze(word)["entries"]
