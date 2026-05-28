# Gemara Pen

A context-aware Aramaic & Hebrew dictionary for Talmud study.

**The product vision:** a physical OCR scanning pen. A student studying Gemara
points it at a word on the page; the pen scans the word and instantly shows its
definition on a small screen — without breaking learning momentum, and without
handing over a full ArtScroll-style translation. This repository contains the
**software brain** for that pen, plus a working web app you can use on a phone
to test it today.

---

## 1. Architecture at a glance

The code is deliberately split into two layers:

```
┌─────────────────────────────────────────────────────────┐
│  THE BRAIN  (offline, no internet)                        │
│                                                           │
│   jastrow.py          dictionary + morphology engine      │
│   data/jastrow.json   bundled dictionary (28,373 entries) │
│                                                           │
│   → This is what runs ON the pen. Port these two files.   │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  THE WEB LAYER  (online, for phone testing + prototype)   │
│                                                           │
│   app.py              Flask REST API + serves the UI      │
│   translator.py       Sefaria passage search (needs net)  │
│   templates/index.html  the web UI                        │
└─────────────────────────────────────────────────────────┘
```

**Key point for the pen:** the dictionary lookup is 100% offline. It needs no
internet, no API keys, no server. The only piece that requires the network is
the optional Sefaria passage search, which is a study feature of the web app —
not part of the pen's core function.

---

## 2. THE BRAIN — `jastrow.py`

Give it a word, get back definitions. That is the whole job.

### Public functions

```python
from jastrow import analyze, lookup, detect_language, strip_nikud

# Recommended: full structured result
analyze("אוחזין")
# {
#   "query":      "אוחזין",
#   "normalized": "אוחזין",      # nikud stripped
#   "found":      True,
#   "match_type": "root",         # how it matched (see below)
#   "entries": [
#       {"hw": "אָחַז", "def": "to press, seize, hold ...", "lang": "unknown"}
#   ]
# }

# Convenience: just the entries
lookup("אוחזין")   # -> [ {"hw", "def", "lang"}, ... ]
```

### `match_type` — how the word was resolved

| value     | meaning                                                        |
|-----------|----------------------------------------------------------------|
| `exact`   | the word is a dictionary headword exactly as typed             |
| `root`    | prefixes/suffixes were stripped to find the root (e.g. אוחזין→אחז) |
| `prefix`  | partial match — the user typed the start of a root             |
| `none`    | not found                                                      |

This is useful on the pen: when `match_type` is `root`, you can show the user
"showing root form: אחז" so they understand why the headword differs from what
they scanned.

### `lang` — Hebrew vs Aramaic

Each entry is tagged `hebrew`, `aramaic`, `both`, or `unknown`, detected from
Jastrow's own notation (`(b. h.)` = Hebrew; `Targ.`/`ch.` = Aramaic). This
matters because Gemara is mixed: the Mishnah and Rashi are mostly Hebrew, while
the Gemara's give-and-take is Aramaic.

### The morphology engine (root-finding)

Hebrew/Aramaic words appear in conjugated forms that are not dictionary
headwords. The engine strips prefixes (ב, ל, מ, ה, ו, ד, ש, את, אית, ...) and
suffixes (plurals ין/ות/יא, possessives יה/יו/הם, verb endings, ...) to recover
the root, trying longest candidates first so e.g. `התורה` resolves to `תורה`
(not the shorter `תור`, "ox"). It also follows Jastrow's `v.` cross-references
automatically. Current coverage of standard Talmudic vocabulary is roughly 95%.

### Dictionary data format — `data/jastrow.json`

```json
{
  "תורה": [
    { "hw": "תּוֹרָה", "def": "teaching, law, esp. the Law of Moses ..." }
  ],
  "אמר": [
    { "hw": "אֲמַר", "def": "1) as preced. 1). Targ. Gen. I, 3 ..." }
  ]
}
```

- **key** = headword with nikud stripped (the search index)
- **value** = list of entries (a word can have several)
- **hw** = the pointed (vocalized) headword for display
- **def** = the definition text
- `lang` is added at lookup time, not stored in the file.

Source: Marcus Jastrow's *Dictionary of the Targumim, Talmud Bavli, Yerushalmi
and Midrashic Literature* (1903), public domain.

---

## 3. THE WEB LAYER — REST API

Run `app.py` and you get a JSON API. The pen prototype (or any app) can call it.

### `POST /lookup` — dictionary (the brain)

Request:
```json
{ "word": "אוחזין" }
```
Response:
```json
{
  "word": "אוחזין",
  "found": true,
  "match_type": "root",
  "entries": [
    { "hw": "אָחַז", "def": "to press, seize, hold ...", "lang": "unknown" }
  ]
}
```

### `POST /translate` — passage search (needs internet)

Find a word across the Talmud with English translation, from Sefaria.

Request:
```json
{ "word": "מלכא", "tractate": "Berakhot", "daf": "2", "amud": "a" }
```
- `daf` empty → searches the whole tractate
- `tractate: "all"` → searches every tractate (slower; warm the cache first)

Response:
```json
{
  "word": "מלכא", "tractate": "Berakhot", "daf": "2a", "total": 3,
  "all_tractates": false,
  "results": [
    { "segment": 1, "daf": 2, "aramaic": "...", "english": "..." }
  ]
}
```

### `POST /precache` + `GET /precache/status`

Downloads all 37 tractates into memory so subsequent searches are instant.
`/precache` starts a background job and returns immediately; poll
`/precache/status` for `{status, loaded, total}`.

---

## 4. Run it on your phone

The live web app is already deployed (Railway). Open the URL on your phone and
use it directly — this is your test harness.

- **Dictionary tab** — type a word, tap "Look Up in Jastrow". Cards show the
  definition with a Hebrew/Aramaic badge.
- **Search Passages tab** — pick a tractate (or "All Tractates"), optionally a
  daf/amud, and find real Gemara passages containing the word.

---

## 5. Local setup (for the developer)

```bash
pip install -r requirements.txt
python app.py            # dev server on http://localhost:5000
```

To use the brain alone, with no web server at all:
```python
from jastrow import analyze
print(analyze("שבת"))
```

**Deployment:** the `Procfile` runs `gunicorn app:app` and is configured for
Railway (binds `$PORT`, 300s timeout). Pushing to the `main` branch on GitHub
auto-deploys. (`render.yaml` is also present if Render is preferred.)

---

## 6. OCR integration plan (the pen's scanning stage)

The brain takes **text** in and gives **definitions** out. To make the physical
pen, one stage sits in front of it: turning the camera image into a word.

```
[camera image of a word]  →  [OCR]  →  "אוחזין"  →  analyze()  →  [screen]
```

The contract is simple: OCR must output a Hebrew/Aramaic word as a string.
`analyze()` already strips nikud, so the OCR output does not need to be clean of
vowel points. Everything downstream is solved.

### Recommended OCR approach

| Mode                | Engine                                   | Notes |
|---------------------|------------------------------------------|-------|
| **Offline (pen)**   | Tesseract OCR with the `heb` language pack | Runs on-device (Raspberry-Pi-class hardware). The realistic choice for a self-contained pen. |
| **Prototype (phone)** | Cloud OCR (e.g. Google Cloud Vision) or the phone's built-in text recognition | Easiest to get working first; needs internet. Good for proving the concept before hardware. |

### Things the developer should know about Talmud OCR

1. **Typeface.** Standard Gemara is printed in the *Vilna Shas* square Hebrew
   font. Tesseract's default Hebrew model should be tested against it and may
   benefit from fine-tuning on that typeface.
2. **Rashi script.** Rashi and Tosafot commentary use a separate semi-cursive
   typeface that general Hebrew OCR handles poorly. Target the main Gemara text
   first; treat commentary as a later phase.
3. **No nikud.** Standard Gemara text is unvocalized, which actually makes OCR
   *easier* and matches how the brain searches (it strips nikud anyway).
4. **Word isolation.** The pen points at one word; the capture/segmentation step
   should isolate a single word before OCR, or OCR a small region and pick the
   word nearest the pen tip.
5. **Final letters.** Hebrew final forms (ך ם ן ף ץ) must be recognized
   correctly — they are normal in the dictionary index, so no special handling
   is needed in the brain, only accurate OCR.

### Suggested build order

1. Phone prototype: phone camera → cloud OCR → `POST /lookup` → show result.
   Proves the whole pipeline end-to-end with minimal hardware.
2. Swap cloud OCR for on-device Tesseract.
3. Move the brain (`jastrow.py` + `data/jastrow.json`) onto the device for full
   offline operation.
4. Hardware: pen form factor, screen, tip-position word isolation.

---

## 7. Test words

| Word      | Expect                                                        |
|-----------|---------------------------------------------------------------|
| `שבת`     | exact match, tagged **Hebrew & Aramaic**                      |
| `מלך`     | exact match, tagged **Hebrew**                                |
| `אמר`     | exact match, tagged **Aramaic**                               |
| `התורה`   | root match → `תורה` (not the shorter `תור`)                   |
| `אוחזין`  | root match → `אחז`                                            |
| `מחלקן`   | root match → `חלק`                                            |
| `מתניתין` | root match → `מתני`                                           |
| `דאמר`    | root match → `אמר` (strips the ד prefix)                      |
| `רק`      | exact match, real definition (follows the `v.` cross-ref)     |

---

## 8. File map

| File                  | Layer | Purpose                                            |
|-----------------------|-------|----------------------------------------------------|
| `jastrow.py`          | brain | Dictionary + morphology engine. **Offline.**       |
| `data/jastrow.json`   | brain | The bundled dictionary (28,373 headwords).         |
| `app.py`              | web   | Flask REST API + serves the UI.                    |
| `translator.py`       | web   | Sefaria passage search (needs internet).           |
| `templates/index.html`| web   | The web UI.                                        |
| `requirements.txt`    | —     | Python dependencies (flask, requests, gunicorn).   |
| `Procfile`            | —     | Railway/Heroku start command.                      |

---

## 9. Known limitations & next steps

- **Loanwords.** Greek/Latin/Persian words that entered Aramaic (e.g. אפייסיה,
  from Greek) are not in Jastrow. A future fallback to the Comprehensive Aramaic
  Lexicon (CAL) would close this gap.
- **`lang: unknown`.** Some core words carry no explicit Jastrow language marker
  and show no badge. Detection could be improved with a Mishnaic-Hebrew word
  list.
- **Morphology edge cases.** ~95% coverage; rare/irregular forms can still miss.
