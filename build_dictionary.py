"""
build_dictionary.py

Stage 1 — build_corpus(tractate):
  Downloads Sefaria Aramaic + English, records every unique word form
  alongside the shortest Aramaic+English segment pair it appears in.
  Saves: word_contexts.json  {word: {aram, eng, tractate, daf}}

Stage 2 — refine_with_claude():
  Reads word_contexts.json, batches words + their shortest segments,
  calls Claude (Haiku) to extract a 1-5 word gloss for each word.
  Saves: real_dictionary.json  {word: {translation, tractate, daf}}
         unmatched.json        [words Claude could not translate]

Usage:
  python build_dictionary.py               # Megillah, both stages
  python build_dictionary.py Berakhot      # specific tractate
  python build_dictionary.py all           # all 37 tractates (slow)
  python build_dictionary.py --no-refine   # skip Claude step
"""

import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from urllib.parse import quote

import requests

TRACTATES = {
    "Berakhot":      {"seder": "Seder Zeraim",   "max_daf": 64},
    "Shabbat":       {"seder": "Seder Moed",     "max_daf": 157},
    "Eruvin":        {"seder": "Seder Moed",     "max_daf": 105},
    "Pesachim":      {"seder": "Seder Moed",     "max_daf": 121},
    "Yoma":          {"seder": "Seder Moed",     "max_daf": 88},
    "Sukkah":        {"seder": "Seder Moed",     "max_daf": 56},
    "Beitzah":       {"seder": "Seder Moed",     "max_daf": 40},
    "Rosh Hashanah": {"seder": "Seder Moed",     "max_daf": 35},
    "Taanit":        {"seder": "Seder Moed",     "max_daf": 31},
    "Megillah":      {"seder": "Seder Moed",     "max_daf": 32},
    "Moed Katan":    {"seder": "Seder Moed",     "max_daf": 29},
    "Chagigah":      {"seder": "Seder Moed",     "max_daf": 27},
    "Yevamot":       {"seder": "Seder Nashim",   "max_daf": 122},
    "Ketubot":       {"seder": "Seder Nashim",   "max_daf": 112},
    "Nedarim":       {"seder": "Seder Nashim",   "max_daf": 91},
    "Nazir":         {"seder": "Seder Nashim",   "max_daf": 66},
    "Sotah":         {"seder": "Seder Nashim",   "max_daf": 49},
    "Gittin":        {"seder": "Seder Nashim",   "max_daf": 90},
    "Kiddushin":     {"seder": "Seder Nashim",   "max_daf": 82},
    "Bava Kamma":    {"seder": "Seder Nezikin",  "max_daf": 119},
    "Bava Metzia":   {"seder": "Seder Nezikin",  "max_daf": 119},
    "Bava Batra":    {"seder": "Seder Nezikin",  "max_daf": 176},
    "Sanhedrin":     {"seder": "Seder Nezikin",  "max_daf": 113},
    "Makkot":        {"seder": "Seder Nezikin",  "max_daf": 24},
    "Shevuot":       {"seder": "Seder Nezikin",  "max_daf": 49},
    "Avodah Zarah":  {"seder": "Seder Nezikin",  "max_daf": 76},
    "Horayot":       {"seder": "Seder Nezikin",  "max_daf": 14},
    "Zevachim":      {"seder": "Seder Kodashim", "max_daf": 120},
    "Menachot":      {"seder": "Seder Kodashim", "max_daf": 110},
    "Chullin":       {"seder": "Seder Kodashim", "max_daf": 142},
    "Bekhorot":      {"seder": "Seder Kodashim", "max_daf": 61},
    "Arakhin":       {"seder": "Seder Kodashim", "max_daf": 34},
    "Temurah":       {"seder": "Seder Kodashim", "max_daf": 34},
    "Keritot":       {"seder": "Seder Kodashim", "max_daf": 28},
    "Meilah":        {"seder": "Seder Kodashim", "max_daf": 22},
    "Tamid":         {"seder": "Seder Kodashim", "max_daf": 33},
    "Niddah":        {"seder": "Seder Taharot",  "max_daf": 73},
}

GCS_BASE = "https://storage.googleapis.com/sefaria-export/json/Talmud/Bavli"
BATCH_SIZE = 20   # words per Claude API call

# How many batches to send at once. Requests are independent, so this is a
# straight wall-clock division. Override with --workers N.
WORKERS = int(os.environ.get("GEMARA_WORKERS", "8"))

# Shared cross-tractate word cache — see seed_glossary.py.
GLOSSARY_FILE = "glossary.json"

# Model used for every translation call.
MODEL = os.environ.get("GEMARA_MODEL", "claude-opus-5")

# Reasoning effort: low | medium | high | xhigh | max.
# Glossing single words is not deep-reasoning work; "medium" keeps quality
# high without paying for long deliberation on 8,000 words.
EFFORT = os.environ.get("GEMARA_EFFORT", "medium")

# claude-opus-5 list price, USD per million tokens.
PRICE_IN_PER_MTOK  = 5.00
PRICE_OUT_PER_MTOK = 25.00


# ── Utilities ──────────────────────────────────────────────────────────────

def gcs_url(tractate: str, lang: str) -> str:
    seder = TRACTATES[tractate]["seder"]
    return f"{GCS_BASE}/{quote(seder)}/{quote(tractate)}/{quote(lang)}/merged.json"


def fetch_text(url: str) -> list:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()["text"]


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def flatten(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        out = []
        for item in node:
            out.extend(flatten(item))
        return out
    return []


def split_aramaic_words(text: str) -> list[str]:
    clean = re.sub(r"<[^>]+>", "", text)
    # Split on whitespace and punctuation, but NOT on geresh (׳) or gershayim (״)
    # when they appear within/after Hebrew letters — those are abbreviations like ה׳
    # We strip leading/trailing geresh/gershayim after splitting instead.
    parts = re.split(
        r"[\s־׀׃׆–—,;:()\[\]\"'\.\!\?\-/]+",
        clean,
    )
    result = []
    for p in parts:
        if not p:
            continue
        # Strip surrounding quotation-mark gershayim (used for Bible quotes)
        # but keep geresh/gershayim that follow Hebrew letters (abbreviations)
        p = re.sub(r'^״|״$', '', p)   # strip leading/trailing gershayim
        if p and re.search(r"[א-ת]", p):
            result.append(p)
    return result


def daf_label(daf_idx: int) -> str:
    """Convert GCS list index to Talmudic daf+amud label (e.g. 60 → '31a')."""
    daf_number = (daf_idx - 2) // 2 + 2
    amud = 'a' if (daf_idx - 2) % 2 == 0 else 'b'
    return f"{daf_number}{amud}"


_STRIP_PREFIXES = ['ו', 'ה', 'ב', 'ל', 'מ', 'כ', 'ד', 'ש']


def extract_root(word: str) -> str:
    """Strip nikud and common single-letter prefixes to approximate the root.
    Only strips a prefix when the remaining form is still ≥ 3 characters."""
    bare = re.sub(r'[֑-ׇ]', '', word).strip()
    for _ in range(3):
        for pfx in _STRIP_PREFIXES:
            if bare.startswith(pfx) and len(bare) - len(pfx) >= 3:
                bare = bare[len(pfx):]
                break
        else:
            break
    return bare


# ── Stage 1: Build corpus ──────────────────────────────────────────────────

def build_corpus(tractate_names: list[str]) -> dict:
    """
    For each tractate, download Aramaic + English and record every unique
    word form alongside the SHORTEST segment it appears in.

    Returns: {word: {"aram": str, "eng": str, "tractate": str, "daf": str}}
    """
    # word → list of (aram_segment, eng_segment, tractate, daf)
    all_contexts: dict[str, list] = defaultdict(list)

    for tractate in tractate_names:
        print(f"\n  Downloading {tractate}…", end=" ", flush=True)
        try:
            heb_list = fetch_text(gcs_url(tractate, "Hebrew"))
            eng_list = fetch_text(gcs_url(tractate, "English"))
        except Exception as e:
            print(f"FAILED ({e})")
            continue

        seg_count = 0
        for daf_idx in range(2, len(heb_list)):
            heb_segs = flatten(heb_list[daf_idx])
            eng_segs = flatten(eng_list[daf_idx] if daf_idx < len(eng_list) else [])
            daf = daf_label(daf_idx)

            for i, heb in enumerate(heb_segs):
                heb = strip_html(heb).strip()
                if not heb:
                    continue
                eng = strip_html(eng_segs[i]).strip() if i < len(eng_segs) else ""
                seg_count += 1

                for word in split_aramaic_words(heb):
                    all_contexts[word].append((heb, eng, tractate, daf))

        print(f"{seg_count} segments, {len([w for w, cs in all_contexts.items() if cs and cs[-1][2] == tractate])} new words")

    # For each word, keep only the entry with the SHORTEST English segment
    # (shortest English = most likely to be a useful gloss; avoids 150-word paragraphs)
    word_contexts: dict[str, dict] = {}
    for word, contexts in all_contexts.items():
        with_eng = [(a, e, t, d) for a, e, t, d in contexts if e]
        if not with_eng:
            # No English anywhere — keep the first Aramaic context
            a, e, t, d = contexts[0]
            word_contexts[word] = {"aram": a, "eng": "", "tractate": t, "daf": d}
        else:
            # Shortest English segment
            a, e, t, d = min(with_eng, key=lambda x: len(x[1].split()))
            word_contexts[word] = {"aram": a, "eng": e, "tractate": t, "daf": d}

    print(f"\n  Total unique word forms: {len(word_contexts)}")
    with open("word_contexts.json", "w", encoding="utf-8") as f:
        json.dump(word_contexts, f, ensure_ascii=False, indent=2)
    print("  Saved → word_contexts.json")
    return word_contexts


# ── Stage 2: Refine with Claude ───────────────────────────────────────────

# ── Shared glossary cache ──────────────────────────────────────────────────

def load_glossary() -> dict:
    """{word: {"t", "lang", "pos"}} for every word ever translated."""
    if os.path.exists(GLOSSARY_FILE):
        with open(GLOSSARY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_glossary(glossary: dict) -> None:
    with open(GLOSSARY_FILE, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2, sort_keys=True)


# ── Usage meter ────────────────────────────────────────────────────────────

_usage_lock = threading.Lock()
USAGE = {"in": 0, "out": 0, "calls": 0}


def _record_usage(usage: dict) -> None:
    with _usage_lock:
        USAGE["in"]    += usage.get("input_tokens", 0)
        USAGE["out"]   += usage.get("output_tokens", 0)
        USAGE["calls"] += 1


def usage_cost() -> float:
    return (USAGE["in"]  / 1_000_000 * PRICE_IN_PER_MTOK +
            USAGE["out"] / 1_000_000 * PRICE_OUT_PER_MTOK)


def usage_report() -> str:
    return (f"{USAGE['calls']} API calls — "
            f"{USAGE['in']:,} in / {USAGE['out']:,} out tokens — "
            f"${usage_cost():.2f}")


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

USER_TEMPLATE = """Translate each word. Reply with JSON only.

{items}"""

# Common English words that don't count as content matches
_STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'to', 'of', 'in',
    'for', 'on', 'with', 'at', 'by', 'from', 'and', 'but', 'or', 'not',
    'so', 'as', 'if', 'that', 'this', 'it', 'its', 'he', 'him', 'his',
    'she', 'her', 'they', 'them', 'their', 'we', 'us', 'you', 'who',
    'which', 'what', 'also', 'then', 'there', 'here', 'no', 'nor',
    'all', 'any', 'some', 'such', 'own', 'same', 'too', 'than', 'into',
    'about', 'up', 'out', 'my', 'me', 'i', 'one', 'two', 'said', 'says',
}


def _content_words(text: str) -> set:
    """Lowercase non-stopword tokens of length > 2."""
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def sefaria_consistent(translation: str, sefaria_eng: str) -> bool:
    """True if translation shares at least one content word with sefaria_eng."""
    if not sefaria_eng:
        return True   # nothing to validate against — assume OK
    trans_words   = _content_words(translation)
    sefaria_words = _content_words(sefaria_eng)
    return bool(trans_words & sefaria_words)


def build_item(i: int, word: str, ctx: dict) -> str:
    aram = ctx["aram"][:120]
    eng  = ctx["eng"][:200]
    return (
        f'{i}. Word: {word}\n'
        f'   Aramaic segment: {aram}\n'
        f'   Sefaria English of segment: {eng}'
    )


def build_retry_item(i: int, word: str, ctx: dict) -> str:
    aram = ctx["aram"][:120]
    eng  = ctx["eng"][:200]
    return (
        f'{i}. Word: {word}\n'
        f'   Aramaic segment: {aram}\n'
        f'   Sefaria English (your translation MUST be consistent with this): "{eng}"'
    )


TOKEN_FILE = "/home/claude/.claude/remote/.session_ingress_token"
API_URL    = "https://api.anthropic.com/v1/messages"


def _get_token() -> str:
    """Read the session Bearer token, or fall back to ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _claude_call(token: str, prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """POST one messages request and return the response text."""
    if token.startswith("sk-ant-api"):
        headers = {
            "x-api-key":         token,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
    else:
        headers = {
            "Authorization":     f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }

    resp = requests.post(
        API_URL,
        headers=headers,
        json={
            "model":         MODEL,
            # Opus 5 thinks by default and thinking tokens count against
            # max_tokens — 1200 was sized for a non-thinking model and would
            # truncate the JSON mid-object.
            "max_tokens":    8000,
            "output_config": {"effort": EFFORT},
            "system":        system,
            "messages":      [{"role": "user", "content": prompt}],
        },
        timeout=300,
    )
    resp.raise_for_status()
    body = resp.json()
    _record_usage(body.get("usage", {}))

    # With thinking on, content[0] is a thinking block — take the text block.
    text = "".join(b.get("text", "") for b in body.get("content", [])
                   if b.get("type") == "text").strip()
    if not text:
        raise ValueError(f"No text block in response (stop_reason="
                         f"{body.get('stop_reason')})")
    return text


def _parse_response(raw: str, batch: list, word_contexts: dict,
                    results: dict, failed_words: list, use_sefaria_check: bool = True):
    """Parse Claude response and populate results. Returns list of words needing retry."""
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON in response: {raw[:200]}")
    glosses = json.loads(json_match.group())

    needs_retry = []
    for i, word in enumerate(batch):
        entry = glosses.get(str(i + 1))
        if not entry:
            failed_words.append(word)
            continue

        # Handle both new format {"t":..,"lang":..} and legacy string format
        if isinstance(entry, dict):
            gloss = entry.get("t", "").strip()
            lang  = entry.get("lang", "aramaic").strip().lower()
            pos   = entry.get("pos", "").strip().lower()
        else:
            gloss = str(entry).strip()
            lang  = "aramaic"
            pos   = ""

        if not gloss or gloss == "?":
            failed_words.append(word)
            continue

        # Sefaria consistency check
        if use_sefaria_check:
            sefaria_eng = word_contexts[word].get("eng", "")
            if not sefaria_consistent(gloss, sefaria_eng):
                needs_retry.append(word)
                continue

        results[word] = {"t": gloss, "lang": lang, "pos": pos}

    return needs_retry


def _call_with_backoff(token: str, prompt: str, system: str, batch_num: int) -> str:
    """Call Claude with exponential backoff on 429 rate-limit errors."""
    for attempt in range(6):
        try:
            return _claude_call(token, prompt, system)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = int(e.response.headers.get("retry-after", 60)) if attempt < 5 else 0
                if attempt == 5:
                    raise
                print(f"\n  Rate limited on batch {batch_num}, waiting {wait}s…")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("unreachable")


def _run_batches(token: str, batches: list, contexts: dict, system: str,
                 use_sefaria_check: bool, label: str, workers: int) -> tuple:
    """
    Send every batch concurrently and merge the results.

    Each worker owns its own results/failed/retry lists, which are merged on the
    main thread as futures complete — nothing is mutated from two threads at once.
    Returns (results, failed, needs_retry).
    """
    results: dict = {}
    failed:  list = []
    needs_retry: list = []
    total_words = sum(len(b) for b in batches)
    done_words  = 0

    def work(idx_batch):
        idx, batch = idx_batch
        items_text = "\n\n".join(
            build_retry_item(i + 1, w, contexts[w]) if not use_sefaria_check
            else build_item(i + 1, w, contexts[w])
            for i, w in enumerate(batch)
        )
        prompt = USER_TEMPLATE.format(items=items_text)
        r: dict = {}
        f: list = []
        raw = _call_with_backoff(token, prompt, system, idx + 1)
        retry = _parse_response(raw, batch, contexts, r, f,
                                use_sefaria_check=use_sefaria_check)
        return r, f, retry

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, ib): ib for ib in enumerate(batches)}
        for fut in as_completed(futures):
            idx, batch = futures[fut]
            try:
                r, f, retry = fut.result()
                results.update(r)
                failed.extend(f)
                needs_retry.extend(retry)
            except Exception as e:
                # One dead batch must not kill the run — record and move on.
                failed.extend(batch)
                print(f"\n  Batch {idx + 1} failed: {e}")

            done_words += len(batch)
            pct = 100 * done_words // max(total_words, 1)
            bar = "\u2588" * (pct // 5) + "\u2591" * (20 - pct // 5)
            print(f"\r  {label} [{bar}] {pct}% — {done_words}/{total_words}"
                  f"  (${usage_cost():.2f})", end="", flush=True)

    print()
    return results, failed, needs_retry


def refine_with_claude(word_contexts: dict, existing: Optional[dict] = None,
                       workers: int = None) -> tuple:
    """
    Translate words in batches, several batches in flight at once.
    Validates each translation against Sefaria English; words that fail
    validation are retried with a Sefaria-anchored prompt.
    Pass existing={word: entry} to skip already-translated words (resume mode).
    Returns ({word: {"t": gloss, "lang": lang, "pos": pos}}, [failed_words]).
    """
    token = _get_token()
    if not token:
        print("  No API token found — cannot refine.")
        return {}, list(word_contexts.keys())

    workers = workers or WORKERS

    # Skip words already translated (resume mode)
    if existing:
        word_contexts = {w: ctx for w, ctx in word_contexts.items() if w not in existing}
        print(f"  Resuming: {len(existing)} already done, {len(word_contexts)} remaining.")

    words = list(word_contexts.keys())
    total = len(words)
    if total == 0:
        print("  Nothing to translate.")
        return {}, []

    batches = [words[i: i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    print(f"\n  Translating {total} words with Claude Sonnet "
          f"({len(batches)} batches, {workers} at a time)…")

    results, failed, all_needs_retry = _run_batches(
        token, batches, word_contexts, SYSTEM_PROMPT,
        use_sefaria_check=True, label="", workers=workers)

    # Retry words that failed the Sefaria consistency check
    if all_needs_retry:
        print(f"\n  Sefaria validation retry: {len(all_needs_retry)} words…")
        retry_contexts = {w: word_contexts[w] for w in all_needs_retry}
        retry_batches  = [all_needs_retry[i: i + BATCH_SIZE]
                          for i in range(0, len(all_needs_retry), BATCH_SIZE)]

        retry_results, retry_failed, _ = _run_batches(
            token, retry_batches, retry_contexts, SEFARIA_RETRY_PROMPT,
            use_sefaria_check=False, label="Retry", workers=workers)

        results.update(retry_results)
        failed.extend(retry_failed)

    return results, failed


# ── Main ───────────────────────────────────────────────────────────────────

def fix_unmatched():
    """Re-translate words in unmatched.json and merge into real_dictionary.json."""
    print("=" * 60)
    print("  FIXING UNMATCHED: Re-translating words that got '?'")
    print("=" * 60)
    with open("unmatched.json", encoding="utf-8") as f:
        unmatched = json.load(f)
    with open("word_contexts.json", encoding="utf-8") as f:
        word_contexts = json.load(f)
    with open("real_dictionary.json", encoding="utf-8") as f:
        real_dictionary = json.load(f)

    # Build sub-context for unmatched words only
    sub_ctx = {w: word_contexts[w] for w in unmatched if w in word_contexts}
    print(f"  {len(sub_ctx)} words to re-translate…")

    glosses, still_failed = refine_with_claude(sub_ctx)

    new_count = 0
    for word, gloss in glosses.items():
        ctx = sub_ctx[word]
        real_dictionary[word] = {
            "translation": gloss,
            "root":        extract_root(word),
            "tractate":    ctx["tractate"],
            "daf":         ctx["daf"],
        }
        new_count += 1

    with open("real_dictionary.json", "w", encoding="utf-8") as f:
        json.dump(real_dictionary, f, ensure_ascii=False, indent=2)

    remaining = [w for w in unmatched if w not in glosses]
    with open("unmatched.json", "w", encoding="utf-8") as f:
        json.dump(remaining, f, ensure_ascii=False, indent=2)

    print(f"\n  Added {new_count} new translations → real_dictionary.json ({len(real_dictionary)} total)")
    print(f"  Still unmatched: {len(remaining)}")


def main():
    args        = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_refine   = "--no-refine"   in sys.argv
    skip_corpus = "--skip-corpus" in sys.argv   # reuse existing word_contexts.json
    fix_mode    = "--fix-unmatched" in sys.argv  # re-translate unmatched words only

    if fix_mode:
        fix_unmatched()
        return

    tractate_arg = args[0] if args else "Megillah"

    if tractate_arg == "all":
        tractates = list(TRACTATES.keys())
    elif tractate_arg in TRACTATES:
        tractates = [tractate_arg]
    else:
        print(f"Unknown tractate: {tractate_arg!r}")
        sys.exit(1)

    if skip_corpus:
        print("=" * 60)
        print("  STAGE 1: Skipped — loading existing word_contexts.json")
        print("=" * 60)
        with open("word_contexts.json", encoding="utf-8") as f:
            word_contexts = json.load(f)
        print(f"  Loaded {len(word_contexts)} word forms")
    else:
        print("=" * 60)
        print(f"  STAGE 1: Building corpus — {', '.join(tractates)}")
        print("=" * 60)
        word_contexts = build_corpus(tractates)

    if no_refine or not _get_token():
        if not _get_token():
            print("\n  (No API token found — skipping Claude refinement)")
        _save_raw(word_contexts)
        return

    print("\n" + "=" * 60)
    print("  STAGE 2: Extracting word-level translations via Claude")
    print("=" * 60)

    # Load existing translations for resume mode (--skip-corpus re-run)
    existing: dict = {}
    if skip_corpus and os.path.exists("real_dictionary.json"):
        with open("real_dictionary.json", encoding="utf-8") as f:
            existing = json.load(f)

    glosses, failed = refine_with_claude(word_contexts, existing=existing or None)

    # Build real_dictionary.json — merge new glosses with existing
    real_dictionary: dict = dict(existing)  # keep already-translated words
    unmatched: list = []

    for word, ctx in word_contexts.items():
        if word in real_dictionary:
            continue  # already had a translation from existing
        entry = glosses.get(word)
        if entry:
            real_dictionary[word] = {
                "translation": entry["t"],
                "lang":        entry.get("lang", "aramaic"),
                "pos":         entry.get("pos", ""),
                "root":        extract_root(word),
                "tractate":    ctx["tractate"],
                "daf":         ctx["daf"],
            }
        else:
            unmatched.append(word)

    with open("real_dictionary.json", "w", encoding="utf-8") as f:
        json.dump(real_dictionary, f, ensure_ascii=False, indent=2)
    with open("unmatched.json", "w", encoding="utf-8") as f:
        json.dump(unmatched, f, ensure_ascii=False, indent=2)

    # Coverage report
    total  = len(word_contexts)
    got    = len(real_dictionary)
    missed = len(unmatched)
    print("\n" + "=" * 60)
    print("  COVERAGE REPORT")
    print("-" * 60)
    print(f"  Total unique word forms :  {total}")
    print(f"  Words with translation  :  {got}  ({100*got//total}%)")
    print(f"  Words without           :  {missed}  ({100*missed//total}%)")
    print(f"\n  Saved → real_dictionary.json  ({got} entries)")
    print(f"  Saved → unmatched.json        ({missed} entries)")

    # Sample: best entries (shortest translations)
    print("\n  Sample entries:")
    sample = sorted(real_dictionary.items(), key=lambda kv: len(kv[1]["translation"]))[:20]
    for word, info in sample:
        print(f"    {word:<22}  →  {info['translation']}")


def _save_raw(word_contexts: dict) -> None:
    """Save dictionary using raw (segment-level) English as fallback."""
    raw: dict = {}
    no_eng: list = []
    for word, ctx in word_contexts.items():
        if ctx["eng"]:
            raw[word] = {"translation": ctx["eng"], "tractate": ctx["tractate"], "daf": ctx["daf"]}
        else:
            no_eng.append(word)
    with open("real_dictionary.json", "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    with open("unmatched.json", "w", encoding="utf-8") as f:
        json.dump(no_eng, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved raw dictionary → real_dictionary.json  ({len(raw)} entries)")
    print(f"  Saved unmatched      → unmatched.json        ({len(no_eng)} entries)")
    print("\n  NOTE: Translations are segment-level (full sentences).")
    print("  Run with ANTHROPIC_API_KEY set to get 1-5 word glosses.")


if __name__ == "__main__":
    main()
