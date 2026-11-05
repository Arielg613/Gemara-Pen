# MEMORY — shared memory across every Claude session

Ariel works with Claude in more than one place: the terminal on their computer,
and the Claude app on their phone, which runs in a cloud copy of this repo.
Those are separate chats, so this file is the memory they share. Talking to one
should feel like talking to the other.

**Rules for Claude, in every session:**
1. Read this file at the start, together with `STATE.md`.
2. When a new preference, decision, idea or worth-keeping fact comes up, add it
   here as the conversation goes. Don't wait to be asked. Keep each entry short
   and put today's date on it.
3. Commit and push it, so the other session sees it. Before editing, run
   `git pull` so you don't overwrite what the other session added.
4. Don't delete an entry. If one turns out wrong, mark it superseded and say why.

`CLAUDE.md` holds the pipeline rules. `STATE.md` says which tractates are done.
This file holds everything else: who Ariel is, how they like to work, and the
ideas in flight.

---

## Project history — already built (check here before re-brainstorming)
The repo was cut down to just the dictionary builder on 2026-05-31 (commit
`95cb326`). Everything below was built **before** that cut and still exists in
git history. To bring a file back: `git show 09baf13:<path>`, or
`git checkout 09baf13 -- <path>`.
- **Jastrow "brain"** (`jastrow.py`, `morphology.py`, `data/jastrow.json`):
  28,373 headwords, works offline. Strips prefixes and suffixes to find the root
  and follows cross-references. About 95% coverage of Talmud vocabulary.
- **Phone prototype** (`mobile/`, React Native/Expo): camera OCR (ML Kit),
  scan line, zoom, auto-scan → Jastrow lookup, plus a Hebrew/Aramaic badge.
- **Web app** (`app.py`, `templates/index.html`, `translator.py`): Flask app with
  photo upload, Rashi OCR and Sefaria passage search. It was deployed on
  Render/Railway (gemarapen.up.railway.app — may be down now).
- **Context-aware pieces:** `tractate_sense.json` (sense of a word per tractate),
  `phrases.json`, `context_embedder.py` (TF-IDF, ready for the BEREL model),
  `pen_test.py` (pen test console).
- **`DEVELOPER_PROMPT.md`**: handoff for a hardware/OCR developer. Build order:
  phone prototype → offline Tesseract → brain on the device → pen hardware.
- **After the cut (still in the repo):** the per-word, per-daf dictionary
  pipeline (Sonnet, checked against Sefaria), lookup indexes, abbreviations,
  and a searchable web dictionary at `docs/index.html` (GitHub Pages).
  Megillah, Berakhot and Shabbat are done.
- **Not done yet:** Mishnayot and Shulchan Aruch (Gemara only so far),
  auto-location by scanning, and any physical hardware.

## Preferences — how Ariel likes to work
- 2026-11-05 — Uses the terminal most of the time. Uses the phone app on the go,
  mainly for brainstorming.
- 2026-11-05 — Wants one continuous working relationship across devices, not
  separate chats that each start from zero.

## Decisions
- 2026-11-05 — Devices stay in sync through this repo (`MEMORY.md` + `STATE.md`),
  not through a shared chat.
- 2026-11-05 — Long jobs, like full tractate builds, run on Ariel's computer.
  Cloud sessions get wiped (that's how the Eruvin build was lost). Phone sessions
  are for ideas, planning and small code changes.

## Ideas / brainstorm
- 2026-11-05 — **Vision, in Ariel's words:** an offline device (a pen, a box,
  whatever) holding all of Gemara, Mishnayot and Shulchan Aruch, for people
  learning in the beit midrash. You set your location with a knob (e.g. Shulchan
  Aruch, Yoreh De'ah, siman 4), scan a word, and it shows that word's meaning
  for that spot. Translations come from Sefaria, not AI. Working offline matters
  most.
- 2026-11-05 — **Gap to solve:** Sefaria translates whole passages, not single
  words. Three ways to get a word-level meaning:
  (a) a dictionary (Jastrow, public domain, offline) — accurate, but not tied
      to the passage;
  (b) the Sefaria English of the line you scanned, shown next to the word —
      100% Sefaria, but not word-level;
  (c) a per-word gloss lined up with Sefaria's English ahead of time (what this
      repo does now, with Sefaria checking each gloss) — fits the passage, but
      AI-assisted.
  Leaning toward combining them: per-word gloss + Jastrow + the line's Sefaria
  English one click away.
- 2026-11-05 — **Idea: drop the knob with auto-location.** Scan a few words and
  search the whole corpus offline to find where you are (tractate/daf, siman/se'if).
  Keep the knob as a fallback when the match is ambiguous.
- 2026-11-05 — **Prototype path** (already planned in May; see Project history): offline phone app first (camera + OCR + lookup),
  then a hardware pen/box once the data and lookup are proven. Storage is easy:
  the whole corpus is well under 1 GB.

- 2026-11-05 — **Form factor: a slim box with a screen, not a pen.** Ariel thinks of
  it as a portable, offline Merkava-style library: the whole Torah corpus
  (Gemara, Mishnayot, Shulchan Aruch, …). "Pen" is just the working name. A box
  has room for a better camera and screen.
- 2026-11-05 — **Labeling translations:** use the official (Sefaria) translation
  wherever one exists, and AI only to fill the gaps. Every result shows its
  source, e.g. "Official — Sefaria/Steinsaltz" vs "AI". The user always knows
  which one they're looking at.
- 2026-11-05 — **Companion app:** a phone app to check device status and download
  or choose content packs onto the box. The box itself always works offline.
- 2026-11-05 — **Location:** choose where you are by hand, OR scan and it jumps
  there right away (auto-location by matching against the corpus).
- 2026-11-05 — **Scanner insight:** the OCR doesn't need to be perfect, because
  the box already holds the exact text. A rough read of a few words is
  fuzzy-matched against the known corpus, and the match supplies the exact
  word and location. This makes a good scanner realistic with off-the-shelf parts.
- 2026-11-05 — **Hardware approach:** Claude can write all the software
  (camera → OCR → match → display), pick off-the-shelf parts, and design a
  3D-printable case. Claude can't build or manufacture anything physical.
  Cheapest prototype: an old Android phone or cheap tablet locked to one app.
  Next step: a Raspberry Pi + camera module + screen kit that Ariel assembles.
  Factory production would need a hardware partner later.

- 2026-11-05 — **Ariel owns a 3D printer.** Use it for the case, a page stand,
  and the camera mount. Claude designs the files (OpenSCAD/STL); Ariel prints.
- 2026-11-05 — **Which text to start with:** choosing between Gemara and "Kitzur
  Yalkut Yosef" (Ariel's words; might mean Kitzur Shulchan Aruch). What's
  actually available:
  - Gemara: full Sefaria English (Davidson/Steinsaltz), and 3 tractates of
    word dictionaries already built. Recommended starting point.
  - Kitzur Shulchan Aruch (Ganzfried): on Sefaria, Hebrew + full English
    (Metsudah translation, Avrohom Davis, CC-BY). Small (~2.6 MB) and quick to add.
  - Yalkut Yosef / Kitzur Yalkut Yosef: NOT on Sefaria (checked the export). It's
    copyrighted, so there's no official English to use. It would need
    permission or AI-only translation.

- 2026-11-05 — **Test device: Ariel's iPad Mini** (its camera is the scanner).
  First book: Berakhot only.
- 2026-11-05 — **How the Berakhot glosses were made** (older Haiku build, May 2026):
  every unique word form in the tractate was paired with the SHORTEST Sefaria
  segment it appears in (Hebrew + William Davidson English). Batches went to
  Claude, which wrote a 1–5 word gloss for that word, using the Sefaria English
  as a guide. Result: ONE gloss per word form for the whole tractate, repeated
  on every daf it appears on. Weakness: no sense specific to the spot (e.g. עַמּוּד
  on 2a = "pillar", but there it means dawn). Megillah's newer Sonnet build adds
  a check against Sefaria; it's still one gloss per word form.
- 2026-11-05 — **Scanner test app built:** `docs/scan/` (live at
  arielg613.github.io/gemara-pen/scan/). Offline web app: camera or photo →
  Tesseract Hebrew OCR running on the device → fuzzy match against the full
  Berakhot text → jumps to the daf and shows the REAL text (not the OCR). Tap a
  word for the AI gloss (labeled) + Sefaria's official English for that line
  (labeled; bold = literal). Tested on rendered pages, including blurry ones:
  4/4 found the correct daf in ~1–2 s, and it also works with the network off.
  Not yet tested on a real printed Vilna page.
- 2026-11-05 — **Improvement idea:** per-spot glosses. Use the bold (literal) part
  of the Davidson English for the exact line, so each occurrence gets its own
  meaning instead of one per word form.

- 2026-11-05 — **Scanner v2 (terminal):** point-at-a-word mode — red + in the camera;
  Capture opens straight to the word under it; **Live** mode shows the meaning on
  screen as you move (OCR every ~1–2 s). Tap a word in the scanned picture to look it
  up. Added offline Jastrow entries (labeled "Dictionary · Jastrow"), abbreviation
  expansion (גמ׳ → גמרא), prev/next daf, remembers where you left off, and a small
  Settings card (Jastrow, abbreviations — both on). Headless test on rendered pages:
  4/4 dafs found, 97/97 crosshair words correct. Still not tried on a real printed page.
- 2026-11-05 — **Jastrow weak spots:** some verbs miss (קוֹרִין → wrong entry, since
  Jastrow files it under קרא) and it gives a root's general sense, not the one in
  context (בערבין → "mix", not "evening"). The AI gloss stays the main answer.

- 2026-11-05 — **Scanner now lives on Vercel: https://gemara-scanner.vercel.app**
  (Ariel asked; Vercel project `gemara-scanner`, connected to this GitHub repo with
  root folder `docs/scan`, so every push to main redeploys it). GitHub Pages copy still exists but Vercel is the one to use.
  Ariel found "Add to Home Screen" didn't work offline. Fixed: a banner shows until
  every file is saved ("✓ Ready offline"), any page load offline falls back to the
  cached app, storage marked persistent, app icon added. On iPhone/iPad the Home
  Screen icon keeps its OWN copy, so open it once with Wi-Fi and wait for "✓ Ready
  offline". Tested: with the network cut, reload + scan + word lookup all work.

- 2026-11-05 — **Jastrow accuracy:** Ariel said Jastrow isn't accurate. Now an entry
  is shown only when its short meaning shares a word with Sefaria's literal (bold)
  English for that line; still wrong ~1 in 10, so it's OFF by default (Settings switch).

- 2026-11-05 — **Personal use only, not for sale (Ariel's words).** So non-commercial
  licensed sources (CC-BY-NC, e.g. most Sefaria translations) are fine to use. The
  "selling needs permission" concern below only matters if that ever changes.

- 2026-11-05 — **Jastrow dropped (Ariel: "forget about Jastrow").** Removed from the
  scanner app. Don't bring it back unless he asks. The files are still in git history
  (commit 52314dc: docs/scan/jastrow.js, jastrow.json, build_jastrow_data.py).
- 2026-11-05 — **Personal use only, not for sale (Ariel's words).** So non-commercial
  licensed sources (CC-BY-NC, e.g. most Sefaria translations) are fine to use. The
  "selling needs permission" concern below only matters if that ever changes.

- 2026-11-05 — **Recent scans view (Ariel asked):** every Capture / photo / tapped Live
  scan is saved on the device (IndexedDB, last 30): the picture, the raw OCR text, and a
  word-by-word comparison with the real text (green right, yellow misread with the OCR
  form above, grey missed, red junk) plus "% words exactly right". Settings switch, on.
  Use these to judge real-page OCR before changing the scanner.

- 2026-11-05 — **Scans are sent to Claude.** Ariel wants Claude to see every scan so he
  can just say what went wrong. The app POSTs each saved scan to `/api/scan`
  (docs/scan/api/scan.js), which writes `scans/<date>/<id>.json` into the PRIVATE Vercel
  Blob store `gemara-scans` (project gemara-scanner). Each file has the real photo, the
  cleaned image the OCR read, raw OCR text, every OCR word with its box, where the red +
  was, which word got picked, and the word-by-word comparison. Scans taken offline wait
  and send when there's Wi-Fi. **To read them:** `cd ~/Gemara-Pen && T=$(grep ^BLOB_READ_WRITE_TOKEN .env.local
  | cut -d= -f2- | tr -d '"')` then `vercel blob list --rw-token "$T"` and
  `vercel blob get <pathname> --access private -o out.json --rw-token "$T"` (run `vercel env pull` first if .env.local
  is missing; repo root is linked to the project). Endpoint is `api/scan.js` (no clean URLs).
- 2026-11-05 — **Big OCR fix:** real camera pictures have grain and shadows, and Tesseract
  read almost nothing from them (0 words on 3 of 4 noisy test pages). Added a cleanup
  step before OCR (median filter → local-light threshold → drop specks). Hard synthetic
  pages: 3/7 → 7/7 found. Settings flag OPTS.clean (on).

- 2026-11-05 — **Tesseract model test:** the app already uses the best Hebrew model in its
  compact form (tesseract.js `heb` 4.0.0_best_int, 0.6 MB). Tried the full-size float
  model (tessdata_best, 3.1 MB): identical accuracy on Ariel's Berakhot 2a page, clean and
  with simulated camera damage, and a bit slower. Not worth it — kept the compact one.
  Even the worst simulated shot still found 2a.

- 2026-11-05 — **First real-page scan worked** (Ariel's iPhone, Live mode, Berakhot 46a):
  found the daf and landed on the right word. What failed was the meaning: בעל → "against"
  (old one-meaning-per-word Haiku gloss) when it's בעל הבית = the host. Ariel: "this has
  to be like only show phrases".
- 2026-11-05 — **Phrase meanings per spot (pilot: 46a).** New `phrases/<Tractate>.json`:
  per daf, one list per Sefaria segment; each chunk = [number of words, meaning in this
  spot], written by Claude against Sefaria's bold literal English. build_scan_data.py
  checks word counts and adds them as `chunks`. Tapping/aiming any word shows the whole
  phrase highlighted + its spot meaning ("Meaning here"); dafs without chunks fall back
  to the old gloss ("General meaning … not checked"). Next: do all of Berakhot this way.

## Open questions
- Licensing (settled for now: personal, non-commercial): Sefaria translations are mostly CC-BY or CC-BY-NC. Free to use for
  a non-commercial device. Selling one needs permission from Sefaria or the
  translators.
- English coverage: Bavli (Davidson/Steinsaltz) and Mishnah have full English.
  Shulchan Aruch English on Sefaria is partial — check which sections exist.
- OCR: printed Hebrew on a small camera, with nikud, Rashi script and tiny
  fonts. This is the hardest technical part.

## Log — short notes on what each session did
- 2026-11-05 (terminal) — Moved scanner to Vercel, fixed offline mode.
- 2026-11-05 (terminal) — Scanner v2: point-at-word, Live mode, Jastrow, abbreviations.
- 2026-11-05 (phone) — Built the docs/scan offline scanner test app for the iPad Mini.
- 2026-11-05 (phone) — Pivot discussed: pen → slim box, official-vs-AI labels, companion app, scanner approach.
- 2026-11-05 (phone) — Found the pre-cut work in git history and wrote the Project history section.
- 2026-11-05 (phone) — Brainstormed the overall device vision and saved it above.
- 2026-11-05 (phone) — Created this file and pointed `CLAUDE.md` at it.
