#!/usr/bin/env python3
"""
Fetches all sections of the Jastrow Hebrew/Aramaic Abbreviations from Sefaria
and saves them to jastrow_abbreviations_raw.json.

Usage: python3 fetch_jastrow_abbrev.py
"""
import json
import time
import urllib.request
import urllib.error

BASE_URL = "https://www.sefaria.org/api/texts/Jastrow,_Hebrew_or_Aramaic_Abbreviations.{n}?context=0"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GemaraPen/1.0)",
    "Accept": "application/json",
}

results = []

for n in range(1, 288):
    url = BASE_URL.format(n=n)
    data = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            if attempt == 3:
                print(f"  Section {n}: failed after 4 attempts — {e}")
            else:
                time.sleep(2 ** attempt)

    if data is None:
        continue

    text = data.get("text", "")
    if not text:
        print(f"  Section {n}: empty — stopping early")
        break

    results.append({"section": n, "text": text})
    print(f"  Section {n}: ok — {str(text)[:70]!r}")
    time.sleep(0.15)

output_path = "jastrow_abbreviations_raw.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nDone — {len(results)} sections saved to {output_path}")
