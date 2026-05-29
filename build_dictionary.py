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
import time
from collections import defaultdict
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
BATCH_SIZE = 30   # words per Claude API call


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
    parts = re.split(
        r"[\s־׀׃׆׳״–—"
        r",;:()\[\]\"'\.\!\?\-/]+",
        clean,
    )
    return [p for p in parts if p and re.search(r"[א-ת]", p)]


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
            daf = str(daf_idx)

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

SYSTEM_PROMPT = """You are a Talmudic Aramaic/Hebrew lexicographer.

For each numbered item you receive, you will be given:
  - An Aramaic word (with nikud/vowel points)
  - The Aramaic sentence it appears in
  - The English translation of that sentence

Your job: extract a short (1 to 5 words) English gloss for the individual Aramaic word.

Rules:
- Give ONLY the core meaning of the word itself — not the whole sentence.
- If the word is a name (a person or place), return the name as-is.
- If the word is a grammatical particle (like "and", "of", "that"), say so.
- If you genuinely cannot determine the word's meaning from context, return "?".
- Be consistent: the same root word should get the same basic gloss.

Respond ONLY with a JSON object mapping each number (as a string) to its gloss.
Example response: {"1": "said", "2": "king", "3": "and", "4": "Rabbi"}"""

USER_TEMPLATE = """Translate each word. Reply with JSON only.

{items}"""


def build_item(i: int, word: str, ctx: dict) -> str:
    aram = ctx["aram"][:120]    # limit segment length for token efficiency
    eng  = ctx["eng"][:200]
    return (
        f'{i}. Word: {word}\n'
        f'   Aramaic segment: {aram}\n'
        f'   English of segment: {eng}'
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


def _claude_call(token: str, prompt: str) -> str:
    """POST one messages request and return the response text."""
    # Determine header style: sk-ant- prefix = API key, otherwise Bearer JWT
    if token.startswith("sk-ant-"):
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
            "model":      "claude-haiku-4-5-20251001",
            "max_tokens": 600,
            "system":     SYSTEM_PROMPT,
            "messages":   [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def refine_with_claude(word_contexts: dict) -> tuple[dict, list]:
    """
    Call Claude Haiku in batches to extract word-level glosses.
    Returns ({word: gloss}, [failed_words]).
    """
    token = _get_token()
    if not token:
        print("  No API token found — cannot refine.")
        return {}, list(word_contexts.keys())

    words = list(word_contexts.keys())
    total = len(words)
    print(f"\n  Refining {total} words with Claude ({(total // BATCH_SIZE) + 1} batches)…")

    results: dict[str, str] = {}
    failed:  list[str]      = []

    for batch_start in range(0, total, BATCH_SIZE):
        batch = words[batch_start: batch_start + BATCH_SIZE]
        items_text = "\n\n".join(
            build_item(i + 1, w, word_contexts[w])
            for i, w in enumerate(batch)
        )
        prompt = USER_TEMPLATE.format(items=items_text)

        for attempt in range(3):
            try:
                raw = _claude_call(token, prompt)

                # Parse JSON — Claude sometimes wraps in ```json ... ```
                json_match = re.search(r"\{.*?\}", raw, re.DOTALL)
                if not json_match:
                    raise ValueError(f"No JSON in response: {raw[:200]}")
                glosses = json.loads(json_match.group())

                for i, word in enumerate(batch):
                    gloss = glosses.get(str(i + 1), "?").strip()
                    if gloss and gloss != "?":
                        results[word] = gloss
                    else:
                        failed.append(word)
                break   # success

            except Exception as e:
                if attempt == 2:
                    print(f"\n  Batch {batch_start//BATCH_SIZE + 1} failed: {e}")
                    failed.extend(batch)
                else:
                    time.sleep(2 ** attempt)

        # Progress bar
        done = batch_start + len(batch)
        pct  = 100 * done // total
        bar  = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct}% — {done}/{total}", end="", flush=True)

    print()
    return results, failed


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_refine  = "--no-refine" in sys.argv

    tractate_arg = args[0] if args else "Megillah"

    if tractate_arg == "all":
        tractates = list(TRACTATES.keys())
    elif tractate_arg in TRACTATES:
        tractates = [tractate_arg]
    else:
        print(f"Unknown tractate: {tractate_arg!r}")
        sys.exit(1)

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
    glosses, failed = refine_with_claude(word_contexts)

    # Build real_dictionary.json
    real_dictionary: dict = {}
    unmatched: list = []

    for word, ctx in word_contexts.items():
        gloss = glosses.get(word, "")
        if gloss:
            real_dictionary[word] = {
                "translation": gloss,
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
