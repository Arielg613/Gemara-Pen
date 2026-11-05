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

## Open questions
- Licensing: Sefaria translations are mostly CC-BY or CC-BY-NC. Free to use for
  a non-commercial device. Selling one needs permission from Sefaria or the
  translators.
- English coverage: Bavli (Davidson/Steinsaltz) and Mishnah have full English.
  Shulchan Aruch English on Sefaria is partial — check which sections exist.
- OCR: printed Hebrew on a small camera, with nikud, Rashi script and tiny
  fonts. This is the hardest technical part.

## Log — short notes on what each session did
- 2026-11-05 (phone) — Found the pre-cut work in git history and wrote the Project history section.
- 2026-11-05 (phone) — Brainstormed the overall device vision and saved it above.
- 2026-11-05 (phone) — Created this file and pointed `CLAUDE.md` at it.
