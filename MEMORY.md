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
_(nothing yet)_

## Open questions
_(nothing yet)_

## Log — short notes on what each session did
- 2026-11-05 (phone) — Created this file and pointed `CLAUDE.md` at it.
