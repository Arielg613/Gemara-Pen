"""
build_sample.py — builds first N dafs of a tractate, outputs a standalone file.
Usage: python build_sample.py Megillah 5
"""

import json
import os
import re
import sys
import time
from collections import defaultdict
from urllib.parse import quote

import requests

# Copy needed config from build_dictionary.py
TRACTATES = {
    "Megillah": {"seder": "Seder Moed", "max_daf": 32},
    "Berakhot": {"seder": "Seder Zeraim", "max_daf": 64},
    "Shabbat":  {"seder": "Seder Moed",   "max_daf": 157},
}

GCS_BASE   = "https://storage.googleapis.com/sefaria-export/json/Talmud/Bavli"
BATCH_SIZE = 30

TOKEN_FILE = "/home/claude/.claude/remote/.session_ingress_token"
API_URL    = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are a Talmudic Aramaic/Hebrew lexicographer.

For each numbered item you receive, you will be given:
  - A word (with nikud/vowel points)
  - The Aramaic/Hebrew sentence it appears in
  - The Sefaria English translation of that sentence

Your job: for each word return THREE things:
  1. "t" — a short (1 to 5 words) English gloss for the individual word
  2. "lang" — the language of the word, one of:
       "aramaic"  — Talmudic Aramaic
       "hebrew"   — Mishnaic or Biblical Hebrew
       "greek"    — Greek or Latin loanword (e.g. אפותיקי, סנהדרין, אסטרטגוס)
       "persian"  — Persian or Babylonian loanword
       "other"    — any other foreign origin or uncertain
  3. "pos" — part of speech, one of:
       "noun"      — noun or noun phrase
       "verb"      — verb in any conjugation
       "particle"  — preposition, conjunction, article, or grammatical particle
       "pronoun"   — personal, demonstrative, or relative pronoun
       "adjective" — adjective or adverb
       "name"      — proper name (person, place, tractate)

Rules for translation:
- Give ONLY the core meaning of the word itself — not the whole sentence.
- If the word is a name (person or place), return the name as-is.
- If the word is a grammatical particle (like "and", "of", "that"), say so.
- If the word is an abbreviation (contains ׳ or ״), also provide the full Hebrew/Aramaic form in parentheses. Example: ה׳ → "God (הַשֵּׁם)", כו׳ → "etc. (וְכוּלֵּי)".
- If you genuinely do not know the word, return exactly "?" — do not guess.
- Be consistent: the same root word should get the same basic gloss.
- Your translation should use vocabulary CONSISTENT with the provided Sefaria English.

Respond ONLY with a JSON object mapping each number (as a string) to an object with "t", "lang", and "pos".
Example: {"1": {"t": "said", "lang": "aramaic", "pos": "verb"}, "2": {"t": "king", "lang": "hebrew", "pos": "noun"}, "3": {"t": "Sanhedrin", "lang": "greek", "pos": "name"}}"""

SEFARIA_RETRY_PROMPT = """You are a Talmudic Aramaic/Hebrew lexicographer.

For each item, the Sefaria English translation of the passage is provided.
Your word translation MUST use vocabulary consistent with that English translation.
Translate ONLY the specific word — not the whole sentence.

Rules:
- 1 to 5 words only for the translation
- If it is a name, return the name as-is
- If you genuinely do not know the word, return exactly "?" — do not guess
- Your word choice must align with the Sefaria passage translation provided
- Also identify the language: "aramaic", "hebrew", "greek", "persian", or "other"
- Also identify the part of speech: "noun", "verb", "particle", "pronoun", "adjective", or "name"

Respond ONLY with a JSON object mapping each number (as a string) to an object with "t", "lang", and "pos".
Example: {"1": {"t": "fed him", "lang": "hebrew", "pos": "verb"}, "2": {"t": "court", "lang": "aramaic", "pos": "noun"}}"""

_STOPWORDS = {
    'a','an','the','is','are','was','were','be','been','being','have','has','had',
    'do','does','did','will','would','could','should','may','might','must','shall',
    'can','to','of','in','for','on','with','at','by','from','and','but','or','not',
    'so','as','if','that','this','it','its','he','him','his','she','her','they',
    'them','their','we','us','you','who','which','what','also','then','there','here',
    'no','nor','all','any','some','such','own','same','too','than','into','about',
    'up','out','my','me','i','one','two','said','says',
}

_SOFIT = str.maketrans('ךםןףץ', 'כמנפצ')


def normalize(text):
    bare = re.sub(r'[֑-ׇ]', '', text)
    return bare.translate(_SOFIT)


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
    parts = re.split(r'[\s־׀׃׆–—,;:()\[\]"\'\.!\?/\-]+', clean)
    result = []
    for p in parts:
        if not p:
            continue
        p = re.sub(r'^״|״$', '', p)
        if p and re.search(r'[א-ת]', p):
            result.append(p)
    return result


def daf_label(idx):
    n = (idx - 2) // 2 + 2
    side = 'a' if (idx - 2) % 2 == 0 else 'b'
    return f"{n}{side}"


def _get_token():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _claude_call(token, prompt, system=SYSTEM_PROMPT):
    if token.startswith("sk-ant-api"):
        headers = {"x-api-key": token, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        headers = {"Authorization": f"Bearer {token}", "anthropic-version": "2023-06-01", "content-type": "application/json"}
    resp = requests.post(API_URL, headers=headers, json={
        "model": "claude-sonnet-4-6", "max_tokens": 800,
        "system": system, "messages": [{"role": "user", "content": prompt}],
    }, timeout=60)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def _content_words(text):
    tokens = re.findall(r'[a-zA-Z]+', text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def sefaria_consistent(translation, sefaria_eng):
    if not sefaria_eng:
        return True
    return bool(_content_words(translation) & _content_words(sefaria_eng))


def translate_words(word_contexts, token):
    words = list(word_contexts.keys())
    total = len(words)
    print(f"  Translating {total} words ({(total // BATCH_SIZE) + 1} batches)…")

    results = {}
    failed = []
    needs_retry = []

    for batch_start in range(0, total, BATCH_SIZE):
        batch = words[batch_start:batch_start + BATCH_SIZE]
        items = "\n\n".join(
            f"{i+1}. Word: {w}\n   Aramaic segment: {word_contexts[w]['aram'][:120]}\n   Sefaria English: {word_contexts[w]['eng'][:200]}"
            for i, w in enumerate(batch)
        )
        prompt = f"Translate each word. Reply with JSON only.\n\n{items}"

        for attempt in range(3):
            try:
                raw = _claude_call(token, prompt)
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                if not m:
                    raise ValueError("No JSON")
                glosses = json.loads(m.group())
                for i, word in enumerate(batch):
                    entry = glosses.get(str(i + 1))
                    if not entry:
                        failed.append(word)
                        continue
                    if isinstance(entry, dict):
                        gloss = entry.get("t", "").strip()
                        lang  = entry.get("lang", "aramaic").strip().lower()
                        pos   = entry.get("pos", "").strip().lower()
                    else:
                        gloss, lang, pos = str(entry).strip(), "aramaic", ""
                    if not gloss or gloss == "?":
                        failed.append(word)
                        continue
                    if not sefaria_consistent(gloss, word_contexts[word].get("eng", "")):
                        needs_retry.append(word)
                        continue
                    results[word] = {"t": gloss, "lang": lang, "pos": pos}
                break
            except Exception as e:
                if attempt == 2:
                    failed.extend(batch)
                else:
                    time.sleep(2 ** attempt)

        done = batch_start + len(batch)
        pct = 100 * done // total
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}%  {done}/{total}", end="", flush=True)

    print()

    if needs_retry:
        print(f"  Retry {len(needs_retry)} words (Sefaria mismatch)…")
        for batch_start in range(0, len(needs_retry), BATCH_SIZE):
            batch = needs_retry[batch_start:batch_start + BATCH_SIZE]
            items = "\n\n".join(
                f"{i+1}. Word: {w}\n   Aramaic: {word_contexts[w]['aram'][:120]}\n   Sefaria (must match): \"{word_contexts[w]['eng'][:200]}\""
                for i, w in enumerate(batch)
            )
            prompt = f"Translate each word. Reply with JSON only.\n\n{items}"
            for attempt in range(3):
                try:
                    raw = _claude_call(token, prompt, system=SEFARIA_RETRY_PROMPT)
                    m = re.search(r'\{.*\}', raw, re.DOTALL)
                    if not m:
                        raise ValueError("No JSON")
                    glosses = json.loads(m.group())
                    for i, word in enumerate(batch):
                        entry = glosses.get(str(i + 1))
                        if not entry:
                            failed.append(word)
                            continue
                        if isinstance(entry, dict):
                            gloss = entry.get("t", "").strip()
                            lang  = entry.get("lang", "aramaic").strip().lower()
                            pos   = entry.get("pos", "").strip().lower()
                        else:
                            gloss, lang, pos = str(entry).strip(), "aramaic", ""
                        if gloss and gloss != "?":
                            results[word] = {"t": gloss, "lang": lang, "pos": pos}
                        else:
                            failed.append(word)
                    break
                except Exception as e:
                    if attempt == 2:
                        failed.extend(batch)
                    else:
                        time.sleep(2 ** attempt)

    return results, failed


def main():
    tractate = sys.argv[1] if len(sys.argv) > 1 else "Megillah"
    num_dafs = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    if tractate not in TRACTATES:
        print(f"Unknown tractate: {tractate}")
        sys.exit(1)

    seder = TRACTATES[tractate]["seder"]
    heb_url = f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/Hebrew/merged.json"
    eng_url = f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/English/merged.json"

    print(f"Downloading {tractate}…")
    heb_list = requests.get(heb_url, timeout=60).json()["text"]
    eng_list = requests.get(eng_url, timeout=60).json()["text"]

    # Collect words from first num_dafs dafs (indices 2 to 2+num_dafs-1)
    word_contexts = {}  # word → {aram, eng, daf}
    daf_order = {}      # daf → [words in order]

    end_idx = min(2 + num_dafs, len(heb_list))
    print(f"Processing dafs 2a–{daf_label(end_idx - 1)} (indices 2–{end_idx-1})…")

    for idx in range(2, end_idx):
        daf = daf_label(idx)
        heb_segs = flatten(heb_list[idx])
        eng_segs = flatten(eng_list[idx] if idx < len(eng_list) else [])
        daf_order[daf] = []

        for i, heb in enumerate(heb_segs):
            heb = strip_html(heb).strip()
            if not heb:
                continue
            eng = strip_html(eng_segs[i]).strip() if i < len(eng_segs) else ""
            for word in split_words(heb):
                if word not in word_contexts:
                    word_contexts[word] = {"aram": heb, "eng": eng, "daf": daf}

    print(f"  {len(word_contexts)} unique word forms across {num_dafs} dafs")

    token = _get_token()
    if not token:
        print("No API token — cannot translate.")
        sys.exit(1)

    glosses, failed = translate_words(word_contexts, token)

    # Build output organized by daf
    bare_to_gloss = {}
    for word, g in glosses.items():
        bare = normalize(word)
        if bare not in bare_to_gloss:
            bare_to_gloss[bare] = {"word": word, **g}

    dafs_out = {}
    for idx in range(2, end_idx):
        daf = daf_label(idx)
        heb_segs = flatten(heb_list[idx])
        seen = set()
        entries = []

        for seg in heb_segs:
            seg = strip_html(seg).strip()
            for word in split_words(seg):
                bare = normalize(word)
                if bare in seen:
                    continue
                seen.add(bare)
                g = bare_to_gloss.get(bare)
                if g:
                    entry = {
                        "word": g["word"],
                        "translation": g["t"],
                        "lang": g["lang"],
                    }
                    if g.get("pos"):
                        entry["pos"] = g["pos"]
                    entries.append(entry)

        dafs_out[daf] = entries

    result = {"tractate": tractate, "dafs": dafs_out}
    out_path = f"/tmp/{tractate}_sample_{num_dafs}dafs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_entries = sum(len(v) for v in dafs_out.values())
    print(f"\nDone. {len(dafs_out)} dafs, {total_entries} entries, {len(failed)} unknown words.")
    print(f"Saved → {out_path}")
    if failed:
        print(f"Unknown words: {failed[:20]}")


if __name__ == "__main__":
    main()
