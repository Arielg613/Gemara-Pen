#!/usr/bin/env python3
"""
fetch_abbreviations.py

Run this ONCE from your local machine (not the cloud server).
Fetches the Jastrow Hebrew/Aramaic Abbreviations list from Sefaria
and saves it to lookup/abbreviations.json in the pen's format.

Usage:
    python fetch_abbreviations.py
"""

import json
import os
import re
import time
import requests

SEFARIA_API = "https://www.sefaria.org/api/texts"
OUTPUT = "lookup/abbreviations.json"


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def strip_nikud(text):
    return re.sub(r"[֑-ׇ]", "", text)


def normalize_key(abbrev):
    """Strip everything except Hebrew letters for dict key."""
    text = strip_nikud(abbrev)
    return re.sub(r"[^א-ת]", "", text)


def fetch_section(ref, retries=3):
    url = f"{SEFARIA_API}/{ref}?context=0"
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise e


def main():
    os.makedirs("lookup", exist_ok=True)

    abbreviations = {}

    # Fetch the Hebrew or Aramaic Abbreviations section of Jastrow
    # It's structured as numbered sections
    print("Fetching Jastrow Hebrew/Aramaic Abbreviations from Sefaria...")

    section = 1
    empty_count = 0

    while empty_count < 3:
        try:
            data = fetch_section(f"Jastrow,_Hebrew_or_Aramaic_Abbreviations.{section}")
            text = data.get("text", "") or data.get("he", "")

            if isinstance(text, list):
                text = " ".join(t for t in text if t)

            text = strip_html(text).strip()

            if not text:
                empty_count += 1
                section += 1
                continue

            empty_count = 0
            print(f"  Section {section}: {text[:80]}...")

            # Each section is one abbreviation entry.
            # Format is typically: "abbrev = full form: English meaning"
            # Parse it and add to our dict
            abbreviations[f"section_{section}"] = {
                "raw": text,
                "section": section
            }

            section += 1
            time.sleep(0.2)  # be polite to Sefaria

        except Exception as e:
            print(f"  Section {section} failed: {e}")
            empty_count += 1
            section += 1

    print(f"\nFetched {len(abbreviations)} raw entries.")

    # Also try List of Abbreviations (English/Latin abbreviations Jastrow uses)
    print("\nFetching Jastrow List of Abbreviations...")
    try:
        data = fetch_section("Jastrow,_List_of_Abbreviations.1")
        print(f"  Got: {str(data.get('text',''))[:200]}")
    except Exception as e:
        print(f"  Failed: {e}")

    # Save raw data for review
    raw_output = OUTPUT.replace(".json", "_raw.json")
    with open(raw_output, "w", encoding="utf-8") as f:
        json.dump(abbreviations, f, ensure_ascii=False, indent=2)

    print(f"\nRaw data saved to {raw_output}")
    print("Share this file and I'll parse it into the proper abbreviations format.")


if __name__ == "__main__":
    main()
