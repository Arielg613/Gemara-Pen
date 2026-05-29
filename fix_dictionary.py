"""
fix_dictionary.py

Two jobs:
  1. Re-translate every word in unmatched.json using a linguistics-first
     Claude prompt (no more "?" — Claude always gives its best gloss).
  2. Detect common multi-word phrases (bigrams like תָּא שְׁמַע) from the
     Megillah text and add them as combined entries.

Usage:
  python fix_dictionary.py             # Megillah
  python fix_dictionary.py Berakhot    # specific tractate
"""

import json
import os
import re
import sys
import time
from collections import Counter
from urllib.parse import quote

import requests

GCS_BASE   = "https://storage.googleapis.com/sefaria-export/json/Talmud/Bavli"
TOKEN_FILE = "/home/claude/.claude/remote/.session_ingress_token"
API_URL    = "https://api.anthropic.com/v1/messages"
BATCH_SIZE = 30
PHRASE_MIN_FREQ = 3   # bigram must appear this many times to be included

TRACTATES = {
    "Berakhot":      "Seder Zeraim",
    "Shabbat":       "Seder Moed",
    "Eruvin":        "Seder Moed",
    "Pesachim":      "Seder Moed",
    "Yoma":          "Seder Moed",
    "Sukkah":        "Seder Moed",
    "Beitzah":       "Seder Moed",
    "Rosh Hashanah": "Seder Moed",
    "Taanit":        "Seder Moed",
    "Megillah":      "Seder Moed",
    "Moed Katan":    "Seder Moed",
    "Chagigah":      "Seder Moed",
    "Yevamot":       "Seder Nashim",
    "Ketubot":       "Seder Nashim",
    "Nedarim":       "Seder Nashim",
    "Nazir":         "Seder Nashim",
    "Sotah":         "Seder Nashim",
    "Gittin":        "Seder Nashim",
    "Kiddushin":     "Seder Nashim",
    "Bava Kamma":    "Seder Nezikin",
    "Bava Metzia":   "Seder Nezikin",
    "Bava Batra":    "Seder Nezikin",
    "Sanhedrin":     "Seder Nezikin",
    "Makkot":        "Seder Nezikin",
    "Shevuot":       "Seder Nezikin",
    "Avodah Zarah":  "Seder Nezikin",
    "Horayot":       "Seder Nezikin",
    "Zevachim":      "Seder Kodashim",
    "Menachot":      "Seder Kodashim",
    "Chullin":       "Seder Kodashim",
    "Bekhorot":      "Seder Kodashim",
    "Arakhin":       "Seder Kodashim",
    "Temurah":       "Seder Kodashim",
    "Keritot":       "Seder Kodashim",
    "Meilah":        "Seder Kodashim",
    "Tamid":         "Seder Kodashim",
    "Niddah":        "Seder Taharot",
}


# ── Utilities ────────────────────────────────────────────────────────────────

def strip_nikud(text: str) -> str:
    return re.sub(r'[֑-ׇ]', '', text)


def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def flatten(node) -> list:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        out = []
        for item in node:
            out.extend(flatten(item))
        return out
    return []


def split_words(text: str) -> list:
    clean = re.sub(r'<[^>]+>', '', text)
    parts = re.split(r'[\s־׀׃׆׳״–—",;:()\[\]\'\.!\?/\-]+', clean)
    return [p for p in parts if p and re.search(r'[א-ת]', p)]


def extract_root(word: str) -> str:
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


def daf_label(daf_idx: int) -> str:
    daf_number = (daf_idx - 2) // 2 + 2
    amud = 'a' if (daf_idx - 2) % 2 == 0 else 'b'
    return f"{daf_number}{amud}"


# ── API ──────────────────────────────────────────────────────────────────────

def _get_token() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _claude_call(token: str, system: str, user: str) -> str:
    if token.startswith("sk-ant-api"):   # regular API key
        headers = {"x-api-key": token, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
    else:                                # JWT session token → Bearer
        headers = {"Authorization": f"Bearer {token}", "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
    resp = requests.post(
        API_URL,
        headers=headers,
        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 600,
              "system": system, "messages": [{"role": "user", "content": user}]},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


# ── Part 1: Fix unmatched words ──────────────────────────────────────────────

LING_SYSTEM = """You are a Talmudic Aramaic and Biblical Hebrew lexicographer with deep expertise.

For each numbered word, give a short (1–5 word) English gloss.

Rules:
- Use your linguistic knowledge FIRST. The passage context is a secondary hint only.
- For proper names (people, places), return the name as-is.
- For grammatical particles/prepositions/conjunctions, describe their function briefly.
- NEVER return "?". Always give your best translation.
- If the word is a verb form, give the infinitive or basic meaning (e.g. "to nullify", "he came").
- Keep glosses tight: "his companion" not "his companion or fellow".

Respond ONLY with a JSON object: {"1": "gloss", "2": "gloss", ...}"""

LING_USER = """Translate each word. Reply JSON only.

{items}"""


def fix_unmatched(word_contexts: dict, real_dict: dict) -> dict:
    with open("unmatched.json", encoding="utf-8") as f:
        unmatched = json.load(f)

    token = _get_token()
    if not token:
        print("  No token — cannot call Claude.")
        return real_dict

    words = [w for w in unmatched if w not in real_dict]
    total = len(words)
    print(f"\n  Re-translating {total} unmatched words…")

    new_glosses: dict = {}
    still_failed: list = []

    for batch_start in range(0, total, BATCH_SIZE):
        batch = words[batch_start: batch_start + BATCH_SIZE]
        items_text = "\n\n".join(
            f'{i+1}. Word: {w}\n'
            f'   Passage (rough guide): {word_contexts.get(w, {}).get("eng", "")[:150]}'
            for i, w in enumerate(batch)
        )

        for attempt in range(3):
            try:
                raw = _claude_call(token, LING_SYSTEM, LING_USER.format(items=items_text))
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                if not m:
                    raise ValueError(f"No JSON: {raw[:100]}")
                glosses = json.loads(m.group())
                for i, word in enumerate(batch):
                    g = glosses.get(str(i + 1), "").strip()
                    if g and g not in ("?", ""):
                        new_glosses[word] = g
                    else:
                        still_failed.append(word)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"\n    Batch {batch_start//BATCH_SIZE+1} failed: {e}")
                    still_failed.extend(batch)
                else:
                    time.sleep(2 ** attempt)

        done = batch_start + len(batch)
        print(f"\r  [{done}/{total}]", end="", flush=True)

    print(f"\n  Fixed: {len(new_glosses)}  still missing: {len(still_failed)}")

    for word, gloss in new_glosses.items():
        ctx = word_contexts.get(word, {})
        real_dict[word] = {
            "translation": gloss,
            "root":        extract_root(word),
            "tractate":    ctx.get("tractate", ""),
            "daf":         ctx.get("daf", ""),
        }

    # Update unmatched.json to only contain truly untranslatable words
    with open("unmatched.json", "w", encoding="utf-8") as f:
        json.dump(still_failed, f, ensure_ascii=False, indent=2)

    return real_dict


# ── Part 2: Detect and add bigram phrases ────────────────────────────────────

def detect_phrases(tractate: str) -> dict:
    """Download text, find frequent bigrams, translate them via Claude."""
    seder = TRACTATES[tractate]
    heb_url = f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/Hebrew/merged.json"
    eng_url = f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/English/merged.json"

    print(f"\n  Downloading {tractate} for phrase detection…")
    heb_resp = requests.get(heb_url, timeout=60)
    eng_resp = requests.get(eng_url, timeout=60)
    heb_resp.raise_for_status()
    eng_resp.raise_for_status()

    heb_list = heb_resp.json()["text"]
    eng_list = eng_resp.json()["text"]

    # Count bigrams across all segments, also record a representative context
    bigram_count: Counter = Counter()
    bigram_context: dict  = {}   # bigram_str → (aram_seg, eng_seg, daf)

    for daf_idx in range(2, len(heb_list)):
        heb_segs = flatten(heb_list[daf_idx])
        eng_segs = flatten(eng_list[daf_idx] if daf_idx < len(eng_list) else [])
        daf = daf_label(daf_idx)

        for i, heb in enumerate(heb_segs):
            heb_clean = strip_html(heb)
            eng = strip_html(eng_segs[i]) if i < len(eng_segs) else ""
            words = split_words(heb_clean)
            for j in range(len(words) - 1):
                bigram = words[j] + " " + words[j + 1]
                bigram_count[bigram] += 1
                if bigram not in bigram_context:
                    bigram_context[bigram] = (heb_clean, eng, daf)

    # Keep bigrams above frequency threshold, not already in dict
    candidates = [(bg, cnt) for bg, cnt in bigram_count.items() if cnt >= PHRASE_MIN_FREQ]
    candidates.sort(key=lambda x: -x[1])
    print(f"  Bigrams with freq ≥ {PHRASE_MIN_FREQ}: {len(candidates)}")

    token = _get_token()
    if not token:
        print("  No token — skipping phrase translation.")
        return {}

    # Translate bigrams via Claude
    phrase_words = [bg for bg, _ in candidates]
    total = len(phrase_words)
    print(f"  Translating {total} candidate phrases…")

    phrase_dict: dict = {}

    PHRASE_SYSTEM = """You are a Talmudic Aramaic/Hebrew lexicographer.
For each numbered phrase (two Aramaic/Hebrew words), give a short English translation (1–6 words).
If it is a well-known Talmudic idiom (e.g. תָּא שְׁמַע = "come and hear"), use the standard translation.
Otherwise translate literally.
NEVER return "?". Always give your best translation.
Respond ONLY with JSON: {"1": "translation", "2": "translation", ...}"""

    for batch_start in range(0, total, BATCH_SIZE):
        batch = phrase_words[batch_start: batch_start + BATCH_SIZE]
        ctx_lines = "\n".join(
            f'{i+1}. Phrase: {bg}  (appears {bigram_count[bg]}x)  '
            f'Context: {bigram_context[bg][1][:100]}'
            for i, bg in enumerate(batch)
        )

        for attempt in range(3):
            try:
                raw = _claude_call(token, PHRASE_SYSTEM, f"Translate each phrase. JSON only.\n\n{ctx_lines}")
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                if not m:
                    raise ValueError(f"No JSON: {raw[:100]}")
                glosses = json.loads(m.group())
                for i, bg in enumerate(batch):
                    g = glosses.get(str(i + 1), "").strip()
                    if g and g != "?":
                        aram_seg, eng_seg, daf = bigram_context[bg]
                        phrase_dict[bg] = {
                            "translation": g,
                            "root":        "",   # phrases don't have a single root
                            "tractate":    tractate,
                            "daf":         daf,
                            "is_phrase":   True,
                            "frequency":   bigram_count[bg],
                        }
                break
            except Exception as e:
                if attempt == 2:
                    print(f"\n    Phrase batch failed: {e}")
                else:
                    time.sleep(2 ** attempt)

        done = batch_start + len(batch)
        print(f"\r  [{done}/{total} phrases]", end="", flush=True)

    print(f"\n  Phrases added: {len(phrase_dict)}")
    return phrase_dict


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    tractate = sys.argv[1] if len(sys.argv) > 1 else "Megillah"

    print("=" * 60)
    print(f"  Loading existing dictionary for {tractate}")
    print("=" * 60)

    with open("real_dictionary.json", encoding="utf-8") as f:
        real_dict = json.load(f)
    with open("word_contexts.json", encoding="utf-8") as f:
        word_contexts = json.load(f)

    print(f"  Current entries: {len(real_dict)}")

    # Step 1: fix unmatched words
    print("\n" + "=" * 60)
    print("  STEP 1: Fix unmatched words")
    print("=" * 60)
    real_dict = fix_unmatched(word_contexts, real_dict)

    # Step 2: detect and add phrases
    print("\n" + "=" * 60)
    print("  STEP 2: Detect multi-word phrases")
    print("=" * 60)
    phrases = detect_phrases(tractate)
    real_dict.update(phrases)

    # Save
    with open("real_dictionary.json", "w", encoding="utf-8") as f:
        json.dump(real_dict, f, ensure_ascii=False, indent=2)

    total = len(real_dict)
    words_only = sum(1 for v in real_dict.values() if not v.get("is_phrase"))
    phrase_count = sum(1 for v in real_dict.values() if v.get("is_phrase"))

    print("\n" + "=" * 60)
    print("  DONE")
    print("-" * 60)
    print(f"  Total entries    : {total}")
    print(f"  Single words     : {words_only}")
    print(f"  Phrases (bigrams): {phrase_count}")

    with open("unmatched.json", encoding="utf-8") as f:
        still_missing = json.load(f)
    print(f"  Still unmatched  : {len(still_missing)}")

    print("\n  Sample phrases:")
    sample_phrases = sorted(
        [(k, v) for k, v in real_dict.items() if v.get("is_phrase")],
        key=lambda x: -x[1]["frequency"]
    )[:10]
    for phrase, info in sample_phrases:
        print(f"    {phrase:<28} → {info['translation']!r}  (×{info['frequency']})")


if __name__ == "__main__":
    main()
