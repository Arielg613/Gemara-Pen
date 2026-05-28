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
    "א", "י", "נ",
    # Aramaic present-tense marker קא (written ק before consonants): קסבר, קתני
    # תי = 3rd/2nd-person imperfect prefix (תיקשי → קשי). More specific than bare ת
    # to avoid stripping real roots like תנא, תורה, תלמוד.
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


def strip_nikud(text: str) -> str:
    """Remove Hebrew vowel points and cantillation marks; trim whitespace."""
    return re.sub(r"[֑-ׇ]", "", text).strip()


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


def _candidates(word: str) -> tuple[list[str], list[str]]:
    """Return (direct_candidates, extension_candidates) in priority order.

    Direct candidates come from stripping real prefixes/suffixes.
    Extension candidates are synthetic ה/א additions tried only after all
    direct forms fail — ה for Hebrew absolutes, א for Aramaic emphatics.
    """
    direct = []

    # Strip suffixes first
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 2:
            stem = word[: -len(suf)]
            direct.append(stem)
            for pre in _PREFIXES:
                if stem.startswith(pre) and len(stem) - len(pre) >= 2:
                    direct.append(stem[len(pre):])
            # Kal active participle: ו in position 1 (e.g. אוחז → אחז)
            if len(stem) >= 3 and stem[1] == "ו":
                without_vav = stem[0] + stem[2:]
                direct.append(without_vav)
                for pre in _PREFIXES:
                    if without_vav.startswith(pre) and len(without_vav) - len(pre) >= 2:
                        direct.append(without_vav[len(pre):])
            # Hollow-root ו removal from positions 2–3 (e.g. תיוב → תיב, שיוע → שיע)
            if len(stem) >= 4:
                for vpos in (2, 3):
                    if vpos < len(stem) and stem[vpos] == "ו":
                        nv = stem[:vpos] + stem[vpos + 1:]
                        if len(nv) >= 2:
                            direct.append(nv)
                            for pre in _PREFIXES:
                                if nv.startswith(pre) and len(nv) - len(pre) >= 2:
                                    direct.append(nv[len(pre):])

    # Strip prefixes alone
    for pre in _PREFIXES:
        if word.startswith(pre) and len(word) - len(pre) >= 2:
            direct.append(word[len(pre):])

    # Deduplicate direct, preserving order
    seen: set = set()
    unique_direct = []
    for c in direct:
        if c not in seen and c != word:
            seen.add(c)
            unique_direct.append(c)

    # Second-level prefix stripping: try one more prefix off each direct candidate.
    # Handles double-prefix words like מדרבנן→מדרב→דרב→רב, דיעבד→יעבד→עבד,
    # and imperfect verbs like תיקשי→יקשי→קשי (once ק,ת added to PREFIXES).
    second: list = []
    for c in list(unique_direct):
        for pre in _PREFIXES:
            if c.startswith(pre) and len(c) - len(pre) >= 2:
                c2 = c[len(pre):]
                if c2 not in seen and c2 != word:
                    seen.add(c2)
                    second.append(c2)
    unique_direct.extend(second)

    # Synthetic extensions: ה (Hebrew absolute) and א (Aramaic emphatic/absolute).
    # Tried only after all direct candidates are exhausted.
    ext = []
    ext_seen: set = seen.copy()
    for c in unique_direct:
        for suffix in ("ה", "א"):
            x = c + suffix
            if not c.endswith(suffix) and x not in ext_seen and x != word:
                ext_seen.add(x)
                ext.append(x)

    return unique_direct, ext


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

    # 2. Strip prefixes/suffixes to find the root.
    # Direct forms longest-first (תורה before תור), then extension forms.
    direct, ext_forms = _candidates(key)
    for candidate in sorted(direct, key=len, reverse=True) + ext_forms:
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
