#!/usr/bin/env python3
"""
Converts rashei_tevot.csv (Sefaria/Dicta Hebrew abbreviations) to
jastrow_abbreviations_raw.json matching the requested format.

Each row: Phrase, Freq, |, Alternate #1 "expansion (count)", ...
We pick the most-cited expansion as the primary translation.
"""
import csv
import json
import re

def parse_alternate(val):
    """Extract just the expansion text, strip count and underscores."""
    val = val.strip()
    if not val:
        return None
    # Remove trailing "(N)" count
    val = re.sub(r'\s*\(\d+\)\s*$', '', val)
    # Replace underscores with spaces
    val = val.replace('_', ' ')
    return val.strip() or None

results = []
section = 0

with open('rashei_tevot_raw.csv', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)  # skip header row

    for row in reader:
        if not row:
            continue
        phrase = row[0].strip()
        if not phrase:
            continue

        # Collect all alternate expansions (columns 3..25, i.e. index 3 onward)
        # Skip index 1 (freq) and index 2 (pipe separator)
        alts = []
        for cell in row[3:]:
            parsed = parse_alternate(cell)
            if parsed:
                alts.append(parsed)

        if not alts:
            continue

        # Primary translation = first alternate (already sorted by frequency desc)
        primary = alts[0]

        section += 1
        text = phrase + " = " + primary
        if len(alts) > 1:
            text += " (also: " + "; ".join(alts[1:4]) + ")"

        results.append({"section": section, "text": text})

with open('jastrow_abbreviations_raw.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Done — {len(results)} abbreviations saved to jastrow_abbreviations_raw.json")
print("Sample entries:")
for r in results[:5]:
    print(f"  {r['section']}: {r['text']}")
