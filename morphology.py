"""
Gemara Pen — Morphological Analyzer

Breaks an Aramaic/Hebrew word into its grammatical components:
root, prepositional prefixes, pronominal suffixes, noun state,
verb binyan, and tense.  Wraps jastrow.py for the actual definition lookup.

Public API:
  analyze_word(word, tractate="")  ->  dict
"""

import re
from jastrow import (
    analyze as jastrow_analyze,
    expand_abbreviation,
    lookup_phrase,
    strip_nikud,
    _QUICK_GLOSSES,
)

# ── Prepositional prefixes — strip left-to-right, longest first ───────────
# Each entry: (prefix_letters, display_meaning)
_PREP_PREFIXES = [
    ("דמן", "of/from"),
    ("מד",  "from-of"),
    ("כד",  "as/when"),
    ("ו",   "and"),
    ("ד",   "of; that; which; who"),
    ("ב",   "in; with; by"),
    ("ל",   "to; for"),
    ("מ",   "from"),
    ("כ",   "like; as"),
    ("ש",   "that; which"),
    ("ה",   "the"),
]

# ── Pronominal suffixes — strip from end, longest first ───────────────────
_PRON_SUFFIXES = [
    ("כון",  "your (pl. m.)"),
    ("הון",  "their (m.)"),
    ("הין",  "their (f.)"),
    ("כין",  "your (pl. f.)"),
    ("נא",   "our; us"),
    ("הם",   "their (m.)"),
    ("הן",   "their (f.)"),
    ("כם",   "your (pl. m.)"),
    ("כן",   "your (pl. f.)"),
    ("יה",   "his; its"),
    ("הא",   "her"),
    ("ה",    "his; her; its"),
    ("ך",    "your (m. sg.)"),
    ("י",    "my"),
    ("ן",    "their; our"),
]

# ── Noun state endings ────────────────────────────────────────────────────
# (ending, state_label, strip_ok_min_remaining_letters)
_NOUN_STATE_ENDINGS = [
    ("ייא", "emphatic pl. (m.)",  2),
    ("יא",  "emphatic pl.",       2),
    ("תא",  "emphatic sg. (f.)",  2),
    ("ון",  "emphatic pl. (f.)",  2),
    ("ין",  "absolute pl. (m.)",  2),
    ("א",   "emphatic sg. (m.)",  2),
    ("ת",   "construct state",    2),
]

# ── Hebrew plural endings ─────────────────────────────────────────────────
_HEB_PLURAL = [
    ("יות", "fem. pl."),
    ("ות",  "fem. pl."),
    ("ים",  "masc. pl."),
]

# ── Verb binyan (stem) prefixes ───────────────────────────────────────────
_BINYAN_PREFIXES = [
    ("אתת", "Ittaf'al"),
    ("אית", "Itpe'el"),
    ("הית", "Itpe'el"),
    ("את",  "Itpe'el"),
    ("א",   "Af'el"),
]

# ── Pe-Yod weak roots: form-after-yod-drop → full root ───────────────────
# The initial י drops in infinitive construct and several imperfect forms.
_PE_YOD = {
    # infinitive construct stems (appear after stripping ל)
    "צאת":  "יצא",   # לצאת → to go out
    "שבת":  "ישב",   # לשבת → to sit
    "לדת":  "ילד",   # לידת → to give birth
    "רדת":  "ירד",   # לרדת → to go down
    "ראת":  "ירא",   # לראת → to fear
    "קחת":  "לקח",   # לקחת — note: root is לקח (pe-lamed, special)
    "צת":   "יצת",   # rare
    # imperfect / short stems
    "צא":   "יצא",
    "שב":   "ישב",
    "לד":   "ילד",
    "רד":   "ירד",
    "סף":   "יסף",
    "טב":   "יטב",
    "צר":   "יצר",
    # pe-nun: nun often assimilates (נפל → יפל in imperfect)
    "פל":   "נפל",
    "פק":   "נפק",
    "תן":   "נתן",
    "שא":   "נשא",
    "גש":   "נגש",
}

# ── Hollow roots: contracted form → expanded root ─────────────────────────
_HOLLOW = {
    "קם":  "קום",
    "שם":  "שים",
    "בא":  "בוא",
    "דן":  "דון",
    "גר":  "גור",
    "נד":  "נוד",
    "ר":   "רוץ",
    "בש":  "בוש",
}

# ── Discourse particles — exact match before any stripping ────────────────
_DISCOURSE = {
    "תא שמע":          "come and hear (introduces a Talmudic proof)",
    "איבעיא להו":      "a dilemma was raised among them",
    "הכי קאמר":        "this is what it means; he means as follows",
    "הני מילי":        "these rules apply when",
    "במאי עסקינן":     "what are we dealing with?",
    "לא קשיא":         "no contradiction — (distinguishes cases)",
    "אלא מאי":         "but then what (does the text teach)?",
    "שמע מינה":        "conclude from this",
    "קא משמע לן":      "this teaches us",
    "לעולם אימא":      "actually, one should say",
    "מכל מקום":        "in any case; nevertheless",
    "ממה נפשך":        "either way; whichever way you look at it",
    "בשלמא":           "it is understandable; granted that",
    "הואיל":           "since; inasmuch as",
    "כל שכן":          "all the more so",
    "על כרחך":         "necessarily; you are forced to say",
    "ודאי":            "certainly; definitely",
    "ספק":             "doubt; uncertainty",
    "דקתני":           "as the Mishnah/Baraita teaches",
}


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _jastrow_strict(stem: str, tractate: str = "") -> dict | None:
    """Look up stem for a PREFIX-STRIPPED candidate.

    Only accepts exact Jastrow headword matches or quick-gloss hits with a
    non-empty definition.  Rejects results found only through Jastrow's own
    internal root/suffix stripping — those are too noisy when combined with
    our own prefix stripping.
    """
    r = jastrow_analyze(stem, tractate)
    if not r["found"]:
        return None
    mt = r.get("match_type", "")
    if mt in ("exact", "quick") and r.get("gloss"):
        return r
    return None


def _jastrow(stem: str, tractate: str = "") -> dict | None:
    """Look up stem; return analyze() result only if a usable gloss exists.

    Used for the ORIGINAL (non-prefix-stripped) word — accepts root/morphology
    matches from Jastrow as well as exact headword hits.
    """
    r = jastrow_analyze(stem, tractate)
    if not r["found"]:
        return None
    if r.get("gloss") or r.get("match_type") in ("exact", "quick"):
        return r
    return None


def _strip_one_prefix(stem: str) -> tuple[str, str] | None:
    """Strip one prepositional prefix. Returns (remainder, prefix_letters) or None."""
    for prefix, _ in _PREP_PREFIXES:
        if stem.startswith(prefix) and len(stem) - len(prefix) >= 2:
            return stem[len(prefix):], prefix
    return None


def _strip_one_pron_suffix(stem: str) -> tuple[str, str] | None:
    """Strip one pronominal suffix. Returns (remainder, suffix_letters) or None."""
    for suffix, _ in _PRON_SUFFIXES:
        if stem.endswith(suffix) and len(stem) - len(suffix) >= 2:
            return stem[: -len(suffix)], suffix
    return None


def _prefix_label(letters: str) -> str:
    for p, meaning in _PREP_PREFIXES:
        if p == letters:
            return f"{letters} = {meaning}"
    return letters


def _suffix_label(letters: str) -> str:
    for s, meaning in _PRON_SUFFIXES:
        if s == letters:
            return f"{letters} = {meaning}"
    return letters


def _noun_label(ending: str) -> str:
    for e, label, _ in _NOUN_STATE_ENDINGS:
        if e == ending:
            return label
    return ""


def _build_translation(prefixes, root_gloss, state, binyan, tense, suffix) -> str:
    """Compose a human-readable translation string."""
    parts = []
    for p in prefixes:
        parts.append(p.split(" = ", 1)[-1])
    if root_gloss:
        parts.append(root_gloss)
    extras = []
    if state:
        extras.append(state)
    if binyan:
        extras.append(binyan)
    if tense:
        extras.append(tense)
    if suffix:
        extras.append(suffix.split(" = ", 1)[-1])
    if extras:
        parts.append(f"[{'; '.join(extras)}]")
    return " + ".join(parts)


# ────────────────────────────────────────────────────────────────────────────
# Main entry point
# ────────────────────────────────────────────────────────────────────────────

def analyze_word(word: str, tractate: str = "") -> dict:
    """
    Full morphological analysis of an Aramaic/Hebrew word.

    Returns a dict:
      word, normalized, found, root, definition, prefixes (list),
      suffix, state, binyan, tense, full_translation, confidence,
      entries (Jastrow list), type
    """
    normalized = strip_nikud(word)

    out = {
        "word":             word,
        "normalized":       normalized,
        "found":            False,
        "root":             "",
        "definition":       "",
        "prefixes":         [],   # list of "ל = to/for"
        "suffix":           "",   # "ה = his/its"
        "state":            "",   # noun state label
        "binyan":           "",   # verb stem name
        "tense":            "",   # infinitive / participle / perfect / imperfect
        "full_translation": "",
        "confidence":       "low",
        "entries":          [],
        "type":             "word",
    }

    # ── 1. Abbreviation ───────────────────────────────────────────────────
    abbrev = expand_abbreviation(normalized)
    if abbrev:
        out.update({
            "found":            True,
            "root":             normalized,
            "definition":       abbrev["en"],
            "full_translation": abbrev.get("full", abbrev["en"]),
            "confidence":       "high",
            "type":             "abbreviation",
        })
        return out

    # ── 2a. Multi-word discourse particle ─────────────────────────────────
    for particle, meaning in _DISCOURSE.items():
        if normalized == particle or normalized.startswith(particle + " "):
            out.update({
                "found":            True,
                "root":             normalized,
                "definition":       meaning,
                "full_translation": meaning,
                "confidence":       "high",
                "type":             "phrase",
            })
            return out

    # ── 2b. Single-word quick gloss / phrase from jastrow.py ─────────────
    phrase = lookup_phrase(normalized)
    if phrase:
        out.update({
            "found":            True,
            "root":             normalized,
            "definition":       phrase["meaning"],
            "full_translation": phrase["meaning"],
            "confidence":       "high",
            "type":             "phrase",
        })
        return out

    if normalized in _QUICK_GLOSSES:
        out.update({
            "found":            True,
            "root":             normalized,
            "definition":       _QUICK_GLOSSES[normalized],
            "full_translation": _QUICK_GLOSSES[normalized],
            "confidence":       "high",
            "type":             "quick",
        })
        return out

    # ── 3. Strip prepositional prefixes ─────────────────────────────────────
    # Pass A: single-prefix strip.  Check _QUICK_GLOSSES, then strict Jastrow.
    # Pass B: double-prefix strip.  Check _QUICK_GLOSSES ONLY (too noisy for Jastrow).
    # Reason: chaining 2+ prefix strips into Jastrow produces false positives
    # (e.g. מ+ל stripped from מלכין yields כין = "here", which is wrong).
    tense = ""

    for pfx, _meaning in _PREP_PREFIXES:
        if not normalized.startswith(pfx) or len(normalized) - len(pfx) < 2:
            continue
        after1 = normalized[len(pfx):]
        p1_tense = "infinitive" if pfx == "ל" else ""

        # ---- single-strip: _QUICK_GLOSSES ----
        if after1 in _QUICK_GLOSSES:
            out.update({
                "found":            True,
                "root":             after1,
                "definition":       _QUICK_GLOSSES[after1],
                "prefixes":         [_prefix_label(pfx)],
                "tense":            p1_tense,
                "confidence":       "high",
                "type":             "quick",
                "full_translation": _build_translation(
                    [_prefix_label(pfx)], _QUICK_GLOSSES[after1], "", "", p1_tense, ""),
            })
            return out

        # ---- single-strip: strict Jastrow (exact headword only) ----
        j = _jastrow_strict(after1, tractate)
        if j:
            _apply(out, j, after1, [pfx], p1_tense, "", "", "", "high")
            return out

    # Pass B — double-prefix, _QUICK_GLOSSES only
    for pfx1, _ in _PREP_PREFIXES:
        if not normalized.startswith(pfx1) or len(normalized) - len(pfx1) < 3:
            continue
        after1 = normalized[len(pfx1):]
        for pfx2, _ in _PREP_PREFIXES:
            if not after1.startswith(pfx2) or len(after1) - len(pfx2) < 2:
                continue
            after2 = after1[len(pfx2):]
            if after2 in _QUICK_GLOSSES:
                pfxs   = [pfx1, pfx2]
                p_tense = "infinitive" if "ל" in pfxs else ""
                out.update({
                    "found":            True,
                    "root":             after2,
                    "definition":       _QUICK_GLOSSES[after2],
                    "prefixes":         [_prefix_label(p) for p in pfxs],
                    "tense":            p_tense,
                    "confidence":       "high",
                    "type":             "quick",
                    "full_translation": _build_translation(
                        [_prefix_label(p) for p in pfxs],
                        _QUICK_GLOSSES[after2], "", "", p_tense, ""),
                })
                return out

    # ── 4. Try exact Jastrow lookup (original word, no stripping) ────────
    j = _jastrow(normalized, tractate)
    if j:
        _apply(out, j, normalized, [], "", "", "", "", "high")
        return out

    # ── 5. Pe-Yod weak root (initial י dropped) ───────────────────────────
    if stem in _PE_YOD:
        root = _PE_YOD[stem]
        j = _jastrow(root, tractate)
        if j:
            if tense == "infinitive":
                tense = "infinitive (pe-yod)"
            elif not tense:
                tense = "pe-yod form"
            _apply(out, j, root, prefixes, tense, "", "", "", "medium")
            return out

    # ── 6. Hollow root expansion ──────────────────────────────────────────
    if stem in _HOLLOW:
        root = _HOLLOW[stem]
        j = _jastrow(root, tractate)
        if j:
            _apply(out, j, root, prefixes, tense or "hollow root form", "", "", "", "medium")
            return out

    # ── 7. Noun state endings ─────────────────────────────────────────────
    for ending, state_label, min_remaining in _NOUN_STATE_ENDINGS:
        if stem.endswith(ending) and len(stem) - len(ending) >= min_remaining:
            candidate = stem[: -len(ending)]
            # Try as-is, then with ה or א extension
            for ext in ("", "ה", "א"):
                j = _jastrow(candidate + ext, tractate)
                if j:
                    root = candidate + ext
                    _apply(out, j, root, prefixes, tense, state_label, "", "", "medium")
                    return out

    # ── 8. Pronominal suffix ─────────────────────────────────────────────
    hit = _strip_one_pron_suffix(stem)
    if hit:
        remainder, suf_letters = hit
        j = _jastrow(remainder, tractate)
        if not j:
            # Try noun state stripping on the remainder
            for ending, state_label, min_rem in _NOUN_STATE_ENDINGS:
                if remainder.endswith(ending) and len(remainder) - len(ending) >= min_rem:
                    cand = remainder[: -len(ending)]
                    j = _jastrow(cand, tractate)
                    if j:
                        suf_display = _suffix_label(suf_letters)
                        _apply(out, j, cand, prefixes, tense, state_label, "", suf_display, "medium")
                        return out
        if j:
            suf_display = _suffix_label(suf_letters)
            _apply(out, j, remainder, prefixes, tense, "", "", suf_display, "medium")
            return out

    # ── 9. Verb binyan prefix ─────────────────────────────────────────────
    for bpfx, binyan_name in _BINYAN_PREFIXES:
        if stem.startswith(bpfx) and len(stem) - len(bpfx) >= 2:
            candidate = stem[len(bpfx):]
            j = _jastrow(candidate, tractate)
            if j:
                _apply(out, j, candidate, prefixes, tense, "", binyan_name, "", "medium")
                return out

    # ── 10. Hebrew plural endings ─────────────────────────────────────────
    for ending, plural_label in _HEB_PLURAL:
        if stem.endswith(ending) and len(stem) - len(ending) >= 2:
            candidate = stem[: -len(ending)]
            j = _jastrow(candidate, tractate)
            if j:
                _apply(out, j, candidate, prefixes, tense, plural_label, "", "", "medium")
                return out

    # ── 11. Fallback: Jastrow's own morphology stripping ─────────────────
    j = jastrow_analyze(normalized, tractate)
    if j["found"]:
        _apply(out, j, j["normalized"], prefixes, tense, "", "", "", "low")
        return out

    # Not found
    out["full_translation"] = "Word not found in dictionary"
    return out


def _apply(out: dict, j: dict, root: str, raw_prefixes: list, tense: str,
           state: str, binyan: str, suffix: str, confidence: str) -> None:
    """Populate out dict from a successful Jastrow result."""
    prefix_labels = [_prefix_label(p) for p in raw_prefixes]
    gloss = j.get("gloss", "")

    out["found"]       = True
    out["root"]        = root
    out["definition"]  = gloss
    out["prefixes"]    = prefix_labels
    out["state"]       = state
    out["binyan"]      = binyan
    out["tense"]       = tense
    out["suffix"]      = suffix
    out["confidence"]  = confidence
    out["entries"]     = j.get("entries", [])
    out["full_translation"] = _build_translation(prefix_labels, gloss, state, binyan, tense, suffix)
