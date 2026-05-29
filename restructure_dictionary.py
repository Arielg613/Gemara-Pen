"""
restructure_dictionary.py

Converts real_dictionary.json from the flat format:
  { "word": { "translation": "...", "root": "...", "tractate": "...", "daf": "..." } }

To the context-aware structured format:
  { "word": { "root": "...", "entries": [ { "translation": "...", "tractate": "...", "daf": "..." } ] } }

Rules:
  - Same word, same translation  → ONE entry (keep earliest daf)
  - Same word, diff translation  → MULTIPLE entries (one per distinct meaning)
  - Sorted alphabetically by consonants (nikud stripped), then by daf within entries
  - Phrases get is_phrase=True and frequency field

When expanding to all tractates later:
  - Run build_dictionary.py + fix_dictionary.py per tractate
  - Then call merge_into_dictionary(new_entries) which adds new entries or
    new meanings to existing words without clobbering what's already there.

Lookup rule (context-aware):
  Given (word, tractate, daf):
    1. Normalize word (strip nikud)
    2. Find matching key in dictionary
    3. Among entries, score each by:
         - +10 if tractate matches
         - +1/(1+abs(daf_dist)) for daf proximity
    4. Return highest-scoring entry's translation
    5. Fallback: return first entry's translation

Usage:
  python restructure_dictionary.py
"""

import json
import re


# ── Hebrew sort key ────────────────────────────────────────────────────────

def strip_nikud(text: str) -> str:
    return re.sub(r'[֑-ׇ]', '', text)


def heb_sort_key(word: str) -> tuple:
    """Sort key: consonants only, space before letters (so phrases sort with their first word)."""
    bare = strip_nikud(word)
    return tuple(ord(c) for c in bare)


# ── Daf utilities ─────────────────────────────────────────────────────────

def daf_to_int(daf: str) -> int:
    """Convert '15b' → 31, '15a' → 30. Used for proximity comparison."""
    m = re.match(r'(\d+)([ab])', daf)
    if not m:
        return 0
    n = int(m.group(1))
    side = 0 if m.group(2) == 'a' else 1
    return n * 2 + side


def daf_sort_key(entry: dict) -> int:
    return daf_to_int(entry.get('daf', '0a'))


# ── Restructure ────────────────────────────────────────────────────────────

def restructure(flat: dict) -> dict:
    """
    Convert flat dict → structured dict with entries array.
    Merges duplicate (word, translation) pairs, keeps distinct translations.
    """
    structured: dict = {}

    for word, info in flat.items():
        translation = info.get('translation', '').strip()
        root        = info.get('root', '')
        tractate    = info.get('tractate', '')
        daf         = info.get('daf', '')
        is_phrase   = info.get('is_phrase', False)
        frequency   = info.get('frequency', None)

        if not translation:
            continue

        entry = {'translation': translation, 'tractate': tractate, 'daf': daf}

        if word not in structured:
            node = {'root': root, 'entries': [entry]}
            if is_phrase:
                node['is_phrase'] = True
            if frequency is not None:
                node['frequency'] = frequency
            structured[word] = node
        else:
            node = structured[word]
            existing_translations = {strip_nikud(e['translation']).lower()
                                     for e in node['entries']}
            norm_new = strip_nikud(translation).lower()

            if norm_new not in existing_translations:
                # New distinct meaning → add entry
                node['entries'].append(entry)
            else:
                # Same translation — keep the earliest daf (keep existing, skip)
                pass

    # Sort each word's entries by daf
    for word, node in structured.items():
        node['entries'].sort(key=daf_sort_key)

    # Sort the dictionary itself alphabetically by Hebrew consonants
    sorted_structured = dict(sorted(structured.items(), key=lambda kv: heb_sort_key(kv[0])))
    return sorted_structured


# ── Context-aware lookup ─────────────────────────────────────────────────

def lookup(dictionary: dict, word: str, tractate: str = '', daf: str = '') -> dict | None:
    """
    Find the best translation for `word` given optional tractate/daf context.

    Returns:
      { 'word': ..., 'translation': ..., 'root': ..., 'tractate': ..., 'daf': ...,
        'all_entries': [...], 'is_phrase': bool }
    or None if word not found.
    """
    # Normalize: try exact match first, then nikud-stripped match
    bare_input = strip_nikud(word)

    node = dictionary.get(word)
    if node is None:
        for key, val in dictionary.items():
            if strip_nikud(key) == bare_input:
                node = val
                word = key
                break

    if node is None:
        return None

    entries = node.get('entries', [])
    if not entries:
        return None

    # Score each entry for context match
    daf_int = daf_to_int(daf) if daf else -1

    best_entry = entries[0]
    best_score = -1

    for entry in entries:
        score = 0
        if tractate and entry.get('tractate') == tractate:
            score += 10
        if daf_int >= 0 and entry.get('daf'):
            dist = abs(daf_to_int(entry['daf']) - daf_int)
            score += 1.0 / (1 + dist)
        if score > best_score:
            best_score = score
            best_entry = entry

    return {
        'word':        word,
        'translation': best_entry['translation'],
        'root':        node.get('root', ''),
        'tractate':    best_entry.get('tractate', ''),
        'daf':         best_entry.get('daf', ''),
        'all_entries': entries,
        'is_phrase':   node.get('is_phrase', False),
    }


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("Loading real_dictionary.json…")
    with open('real_dictionary.json', encoding='utf-8') as f:
        flat = json.load(f)

    print(f"  Input: {len(flat)} entries")

    structured = restructure(flat)

    # Stats
    total_words   = sum(1 for v in structured.values() if not v.get('is_phrase'))
    total_phrases = sum(1 for v in structured.values() if v.get('is_phrase'))
    multi_meaning = sum(1 for v in structured.values() if len(v['entries']) > 1)
    total_entries = sum(len(v['entries']) for v in structured.values())

    print(f"  Output: {len(structured)} unique words/phrases")
    print(f"    Single words  : {total_words}")
    print(f"    Phrases       : {total_phrases}")
    print(f"    Multi-meaning : {multi_meaning}  (same word, different definitions)")
    print(f"    Total entries : {total_entries}")

    with open('real_dictionary.json', 'w', encoding='utf-8') as f:
        json.dump(structured, f, ensure_ascii=False, indent=2)
    print("\nSaved → real_dictionary.json")

    # Demo lookup
    print("\n── Lookup demo ──────────────────────────────────────────")
    test_words = [
        ('מֶלֶךְ',    'Megillah', '10b'),
        ('הָעִיר',    'Megillah', '32a'),
        ('תא שמע',   'Megillah', '4a'),
        ('יָכוֹל',    'Megillah', '15a'),
        ('פַּרְסוֹמֵי', 'Megillah', '3b'),
        ('נִיסָּא',    'Megillah', '12a'),
    ]
    for word, trac, daf in test_words:
        result = lookup(structured, word, trac, daf)
        if result:
            print(f"  {word:<26} [{trac} {daf}]  →  {result['translation']!r}")
        else:
            print(f"  {word:<26}  →  NOT FOUND")

    # Show first 10 entries of sorted dict
    print("\n── First 10 entries (sorted) ────────────────────────────")
    for word, node in list(structured.items())[:10]:
        e = node['entries'][0]
        print(f"  {word:<26}  root={node['root']!r:<10}  → {e['translation']!r}")


if __name__ == '__main__':
    main()
