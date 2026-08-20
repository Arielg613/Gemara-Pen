# Gemara Pen — Dictionary Builder

> **New session? Read `STATE.md` first.** This file is the rules; `STATE.md`
> is where the work actually stands — which tractates are done, what broke
> last, and what to run next.

## What This Repo Does
Builds word-by-word translation dictionaries for every tractate of the Babylonian Talmud.
Output: one JSON file per tractate in `dictionaries/`, plus nikud-free lookup indexes in `lookup/`.

The dictionaries will eventually be loaded onto a physical scanning pen.
The pen hardware, OCR, and firmware are a separate project — not here.

**CRITICAL RULE — Individual words always come first:**
Every single word in the tractate gets its own entry. Phrases (bigrams/trigrams) are
BONUS entries layered on top — they never replace single-word entries.

---

## Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `build_dictionary.py <Tractate>` | Main pipeline — downloads text, translates, outputs `dictionaries/<Tractate>.json` |
| `rebuild_ordered.py <Tractate>` | Post-process: re-order entries, strip duplicates |
| `build_lookup_index.py` | Generate nikud-free lookup files in `lookup/` |

Run order per tractate:
```
python build_dictionary.py Megillah
python rebuild_ordered.py Megillah
python build_lookup_index.py
```

---

## Translation Rules (build_dictionary.py)

### Source text
- Sefaria GCS export (William Davidson / Steinsaltz translation)
- URL: `https://storage.googleapis.com/sefaria-export/json/Talmud/Bavli/{seder}/{tractate}/{lang}/merged.json`
- Download both `Hebrew` (Aramaic text) and `English` (translation)

### Daf labeling
- GCS list index 2 = daf 2a (all tractates start at index 2)
- Formula: `daf = f"{(idx-2)//2 + 2}{'a' if (idx-2)%2==0 else 'b'}"`

### Word extraction
- Split on whitespace and punctuation
- Keep only tokens with at least one Hebrew letter (א–ת)
- Strip HTML tags before splitting

### Translation via Claude Sonnet
- Model: claude-sonnet-4-6 (Sonnet — not Haiku)
- Batch 30 words per API call
- Each word gets: translation (1-5 words) + language tag (aramaic/hebrew/greek/persian/other)
- If word is an abbreviation (contains ׳ or ״): also return full Hebrew form in parentheses
- **If genuinely unknown: return "?" — do NOT guess**
- Sefaria validation: after each batch, translations with zero content-word overlap with
  Sefaria English are automatically retried with a stronger Sefaria-anchored prompt
- Translations are natural and complete:
  - Include prefix meaning: השבת = "the Shabbat", בשבת = "on Shabbat"
  - Include suffix meaning: ביתו = "his house", לביתם = "to their house"
  - Proper names returned as-is: מרדכי = "Mordechai"
  - Talmudic idioms get standard translations: תא שמע = "come and hear"

### Phrase detection
- Scan all segments for 2-word and 3-word sequences
- Keep phrases that appear 3+ times in the tractate
- Mark as `is_phrase: true`

### Dictionary format
```json
{
  "tractate": "Megillah",
  "dafs": {
    "2a": [
      {"word": "מְגִילָּה", "translation": "scroll", "lang": "aramaic", "pos": "noun"},
      {"word": "נִקְרֵאת", "translation": "is read", "lang": "aramaic", "pos": "verb"}
    ]
  }
}
```

Fields per entry:
- `word` — original form with nikud
- `translation` — 1–5 word English gloss
- `lang` — aramaic / hebrew / greek / persian / other
- `pos` — noun / verb / particle / pronoun / adjective / name

### Lookup logic (for future pen firmware)
Given: scanned word + tractate + daf
1. Check `lookup/abbreviations.json` first
2. Normalize scanned word: strip nikud + normalize sofit forms (ך→כ, ם→מ, ן→נ, ף→פ, ץ→צ)
3. Search current daf
4. If not found → adjacent dafs (±3)
5. If not found → whole tractate
6. If not found → `lookup/master.json` (all tractates)

---

## Abbreviations
`lookup/abbreviations.json` — 11,660 entries from rashei_tevot corpus.
Format: `{bare_key: {"abbrev": "ר׳", "full": "רבי", "freq": 173613}}`
TODO: supplement with full Jastrow abbreviation list (run fetch script locally, bring file back)

---

## Tractate order (37 total)
Moed: Berakhot, Shabbat, Eruvin, Pesachim, Yoma, Sukkah, Beitzah,
      Rosh Hashanah, Taanit, **Megillah** ✓, Moed Katan, Chagigah
Nashim: Yevamot, Ketubot, Nedarim, Nazir, Sotah, Gittin, Kiddushin
Nezikin: Bava Kamma, Bava Metzia, Bava Batra, Sanhedrin, Makkot,
         Shevuot, Avodah Zarah, Horayot
Kodashim: Zevachim, Menachot, Chullin, Bekhorot, Arakhin, Temurah,
          Keritot, Meilah, Tamid
Taharot: Niddah
