# Gemara Pen — Project Rules

## End Goal
A physical scanning pen. User sets tractate + daf on the pen, scans a word,
pen returns the correct translation for that word in that specific context.

**CRITICAL RULE — Individual words always come first:**
Every single word in the tractate must have its own dictionary entry so the
pen can always return a translation for any individual scanned word.
Bigrams and trigrams are BONUS entries layered on top — they never replace
single-word entries. A word that only appears inside a phrase still gets its
own standalone entry.

---

## Dictionary Pipeline Rules (per tractate)

### Step 1 — Download source text
- Source: Sefaria GCS export (William Davidson / Steinsaltz translation)
- URL: `https://storage.googleapis.com/sefaria-export/json/Talmud/Bavli/{seder}/{tractate}/{lang}/merged.json`
- Download both `Hebrew` (Aramaic text) and `English` (translation)

### Step 2 — Daf labeling
- GCS list index 2 = daf 2a (all tractates start at index 2)
- Formula: `daf = f"{(idx-2)//2 + 2}{'a' if (idx-2)%2==0 else 'b'}"`
- Example: index 60 → daf 31a

### Step 3 — Word extraction
- Split on whitespace and punctuation
- Keep only tokens that contain at least one Hebrew letter (א–ת)
- Strip HTML tags before splitting

### Step 4 — Translation via Claude Haiku
- Batch 30 words per API call
- Prompt rule: use linguistic knowledge first; English passage is a secondary hint
- Never return "?" — always give best translation
- Translations are NATURAL and complete:
  - Include prefix meaning: השבת = "the Shabbat", בשבת = "on Shabbat"
  - Include suffix meaning: ביתו = "his house", לביתם = "to their house"
  - Proper names returned as-is: מרדכי = "Mordechai"
  - Talmudic idioms get standard translations: תא שמע = "come and hear"

### Step 5 — Phrase detection
- Scan all segments for 2-word sequences (bigrams)
- Keep phrases that appear 3+ times in the tractate
- Translate each phrase via Claude with same natural-translation rule
- Mark as `is_phrase: true`

### Step 6 — Dictionary format
```json
{
  "tractate": "Megillah",
  "dafs": {
    "2a": [
      {"word": "מְגִילָּה", "translation": "scroll"},
      {"word": "נִקְרֵאת", "translation": "is read"}
    ],
    "2b": [...]
  }
}
```
- Each daf is a separate section
- Words in the order they first appear in the text
- Each word appears in every daf it shows up in
- No root field
- No complex nested structures

### Step 7 — Lookup logic (pen firmware)
Given: scanned word + current tractate + current daf
1. Strip nikud from scanned word
2. Search current daf's word list for a nikud-normalized match
3. If found → return that translation
4. If not found → search adjacent dafs (±3 dafs)
5. If still not found → search entire tractate
6. If still not found → search all tractates (cross-tractate fallback)

---

## What NO to do
- No root field (kept getting it wrong)
- No complex entries[] arrays or scoring systems
- No restructuring that adds layers of indirection
- No skipping words — every word and phrase gets a translation

---

## Suggested additions (not yet implemented)

### High priority
1. **Nikud-free lookup index** — build a parallel index stripped of all
   vowel points so the pen can match scanned words even with partial/no nikud
2. **Abbreviations table** — common Talmudic shortenings:
   ת"ל = תנא לישנא / "the text teaches", ק"ו = קל וחומר / "kal vachomer",
   ר' = רבי / "Rabbi", כ"ש = כל שכן / "all the more so", etc.
3. **Trigrams** — 3-word phrases like תא שמע מינה ("come and hear from this"),
   אין הכי נמי ("yes, that is indeed so"), לא קשיא ("no difficulty")

### Medium priority
4. **Sage name index** — separate list of all Talmudic sage names
   (אביי, רבא, רש"י, etc.) so the pen always recognizes a name vs a word
5. **Cross-tractate merge** — after all 37 tractates are done, merge into
   one master dictionary. Same word with different meanings in different
   tractates = multiple entries, lookup returns the one matching current tractate
6. **Word frequency** — track how many times each word appears across
   all tractates. Common words (appears 500+ times) get flagged as
   "core vocabulary" — useful for the pen's onboarding/learning mode

### Lower priority
7. **Mishnah vs Gemara distinction** — Mishnah sections are more Hebrew,
   Gemara is more Aramaic. Could tag each word by which it came from
8. **Audio pronunciation** — once dictionary is complete, add a
   Sephardi/Ashkenazi pronunciation guide per word for the pen's audio output

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
