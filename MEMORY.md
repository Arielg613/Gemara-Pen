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
- 2026-11-05 — **Prototype path:** offline phone app first (camera + OCR + lookup),
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
- 2026-11-05 (phone) — Brainstormed the overall device vision and saved it above.
- 2026-11-05 (phone) — Created this file and pointed `CLAUDE.md` at it.
