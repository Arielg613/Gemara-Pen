#!/usr/bin/env python3
"""
build_lookup_index.py

Generates nikud-free lookup indexes from completed dictionary files.

Output:
  lookup/<Tractate>.json  — per-tractate: {daf: {bare_word: translation}}
  lookup/master.json      — cross-tractate fallback: {bare_word: translation}

Pen lookup algorithm (Step 7 in CLAUDE.md):
  1. Strip nikud from scanned word
  2. Check current daf dict  → O(1)
  3. Check adjacent dafs (±3) → O(1) each
  4. Check all dafs in tractate → O(dafs)
  5. Check master cross-tractate index → O(1)
"""

import json
import os
import re

DICTIONARIES_DIR = "dictionaries"
LOOKUP_DIR = "lookup"


def strip_nikud(text):
    # Unicode range U+0591–U+05C7 covers all Hebrew cantillation + nikud
    return re.sub(r'[֑-ׇ]', '', text)


def build_indexes():
    os.makedirs(LOOKUP_DIR, exist_ok=True)

    dict_files = sorted(f for f in os.listdir(DICTIONARIES_DIR) if f.endswith('.json'))

    if not dict_files:
        print("No dictionary files found in dictionaries/")
        return

    master = {}  # bare_word -> translation (first occurrence wins for fallback)

    print(f"Building lookup indexes for {len(dict_files)} tractate(s)...\n")

    for filename in dict_files:
        tractate = filename.replace('.json', '')
        path = os.path.join(DICTIONARIES_DIR, filename)

        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        tractate_lookup = {}
        total = 0

        for daf, entries in data['dafs'].items():
            daf_lookup = {}
            for entry in entries:
                bare = strip_nikud(entry['word'])
                translation = entry['translation']

                if bare not in daf_lookup:
                    daf_lookup[bare] = translation

                if bare not in master:
                    master[bare] = translation

                total += 1

            tractate_lookup[daf] = daf_lookup

        out_path = os.path.join(LOOKUP_DIR, f"{tractate}.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({'tractate': tractate, 'dafs': tractate_lookup},
                      f, ensure_ascii=False, indent=2)

        unique = sum(len(d) for d in tractate_lookup.values())
        print(f"  {tractate:20s} {len(tractate_lookup):4d} dafs  {unique:7,d} unique bare words")

    master_path = os.path.join(LOOKUP_DIR, 'master.json')
    with open(master_path, 'w', encoding='utf-8') as f:
        json.dump(master, f, ensure_ascii=False, indent=2)

    print(f"\n  {'master':20s}       {len(master):7,d} unique bare words (cross-tractate fallback)")
    print(f"\nAll indexes written to lookup/")


if __name__ == '__main__':
    build_indexes()
