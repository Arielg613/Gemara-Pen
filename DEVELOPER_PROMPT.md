# Prompt to paste into your AI assistant

Copy everything below the line into Claude / ChatGPT / Cursor / whatever you use,
then attach or point it at the GitHub repo.

---

You are helping me build the **Gemara Pen** — a physical OCR scanning pen for
Talmud study. A student points it at an Aramaic/Hebrew word on a page of Gemara
and it instantly shows the definition on a small screen, without breaking their
learning flow and without giving a full translation.

**The dictionary "brain" is already built and working.** Your job is to build
the OCR scanning layer and the pen prototype around it. Do NOT rebuild the
dictionary — use the existing one.

## What already exists

- **GitHub repo:** https://github.com/arielg613/gemara-pen
- **Live web demo:** https://gemarapen.up.railway.app
- **Read `README.md` in the repo first** — it has the full architecture.

The repo is split into two layers:

- **THE BRAIN (offline, no internet):** `jastrow.py` + `data/jastrow.json`.
  Takes a Hebrew/Aramaic word and returns Jastrow dictionary definitions plus a
  Hebrew/Aramaic language tag. 28,373 headwords. It already handles conjugated
  forms (strips prefixes/suffixes to find the root), follows cross-references,
  and strips nikud. ~95% coverage of standard Talmudic vocabulary. This is the
  part that will eventually run on the pen.
- **THE WEB LAYER (online):** `app.py` (Flask REST API + web UI),
  `translator.py` (optional Sefaria passage search).

## The brain's API

```python
from jastrow import analyze
analyze("אוחזין")
# -> {
#   "query": "אוחזין", "normalized": "אוחזין",
#   "found": True, "match_type": "root",   # exact | root | prefix | none
#   "entries": [{"hw": "אָחַז", "def": "...", "lang": "unknown"}]
# }
```

Or over HTTP (already live): `POST /lookup` with body `{"word": "אוחזין"}`.

## The contract you must fulfill

The brain takes **text** in. You build the stage in front of it that turns a
camera image into that text:

```
[camera image of a word] → [OCR] → "אוחזין" → analyze() → [screen]
```

The brain already strips vowel points, so the OCR output does not need to be
clean of nikud. Everything downstream of the text is already solved.

## Build order (do these in sequence)

1. **Phone prototype:** phone camera → OCR → `POST /lookup` → display the
   result. Prove the whole pipeline end-to-end first. Use cloud OCR (Google
   Cloud Vision) or the phone's built-in Hebrew text recognition (iOS Vision /
   Android ML Kit) to start.
2. Swap cloud OCR for on-device **Tesseract** with the `heb` language pack
   (offline-capable).
3. Move the brain (`jastrow.py` + `data/jastrow.json`) onto the device for full
   offline operation.
4. **Hardware:** pen form factor, small screen, and isolating the single word
   nearest the pen tip.

## Talmud OCR specifics you need to know

- Standard Gemara is printed in the **Vilna Shas** square Hebrew font — test and
  possibly fine-tune the OCR model on that typeface.
- **Rashi/Tosafot** commentary uses a different semi-cursive font that general
  Hebrew OCR handles poorly — target the main Gemara text first.
- Standard Gemara text has **no nikud**, which makes OCR easier.
- Recognize Hebrew **final letters** (ך ם ן ף ץ) correctly.
- The pen points at **one word** — isolate a single word, or OCR a small region
  and pick the word closest to the pen tip.

## Your task right now

Start with **step 1: the phone prototype.** Recommend a stack (e.g. React Native
or native iOS/Android), set up camera capture plus Hebrew OCR, call the existing
`/lookup` API, and show the definition with its Hebrew/Aramaic badge. Before
designing the physical hardware, ask me about budget, screen, and battery
constraints.
