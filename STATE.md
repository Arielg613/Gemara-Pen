# STATE — read this first

Catch-up file for a new session. `CLAUDE.md` holds the rules; this file holds
where the work actually stands. Update it whenever a tractate finishes.

Last updated: 2026-08-20

---

## Where things stand

**Done — 3 of 37 tractates**

| Tractate | Dafs | Entries | Model | Has `lang`+`pos` |
|---|---|---|---|---|
| Megillah | 61 | 16,751 | Sonnet | yes |
| Berakhot | 125 | 38,641 | Haiku | no |
| Shabbat | 312 | 65,317 | Haiku | no |

Megillah is the reference build — it is the only one matching the current
format. Berakhot and Shabbat are older Haiku builds carrying only
`word` + `translation`; they still need Sonnet rebuilds to pick up the
`lang` and `pos` fields.

**Not done — 34 tractates.** Next in order: Eruvin, Pesachim, Yoma, Sukkah,
Beitzah, Rosh Hashanah, Taanit, Moed Katan, Chagigah, then Nashim onward.
Full list in `CLAUDE.md`.

**Eruvin was attempted and lost.** The corpus built fine (10,800 unique
words, 3,646 segments) but the translation pass hit HTTP 429 from batch 322
of 361 and the container was reclaimed before results were written. Nothing
was saved. It needs a clean start.

---

## Read this before running a build locally

`build_dictionary.py` calls the Anthropic API directly over HTTPS. It gets
its credential from `_get_token()`, which tries in order:

1. `$ANTHROPIC_API_KEY`
2. `/home/claude/.claude/remote/.session_ingress_token`

Path 2 only exists inside the Claude Code remote container. **On a local
machine there is no token unless you set `ANTHROPIC_API_KEY`,** and the
script will skip the translation stage and fall back to writing raw
sentence-level English.

The project owner has said they do not want to buy a separate API key. So
running the existing script locally as-is will not work. The options are:

- **Set `ANTHROPIC_API_KEY`** — simplest, but costs money per token.
- **Have the local Claude Code session do the translating itself** — instead
  of the script POSTing to the API, have it write batches to a file, let the
  session translate them in-conversation, and write results back. Slower per
  batch, no separate key, no 429s from a parallel API path.

Whoever picks this up should settle this first; everything else is blocked
behind it.

---

## Commands

```bash
pip install -r requirements.txt

python build_dictionary.py Eruvin          # both stages
python build_dictionary.py Eruvin --skip-corpus   # reuse word_contexts.json
python build_dictionary.py --fix-unmatched        # retry words that came back "?"

python rebuild_ordered.py Eruvin           # -> dictionaries/Eruvin.json
python build_lookup_index.py               # -> lookup/*.json + lookup/master.json
```

`--skip-corpus` is the resume path. It reloads `word_contexts.json` and skips
any word already present in `real_dictionary.json`, so a killed run picks up
where it stopped rather than restarting.

---

## Files

**Committed**

```
CLAUDE.md               rules — translation format, lookup logic, tractate order
STATE.md                this file
build_dictionary.py     stage 1 corpus + stage 2 translation (Sonnet, batch 20)
rebuild_ordered.py      real_dictionary.json -> dictionaries/<Tractate>.json
build_lookup_index.py   dictionaries/ -> lookup/ (nikud-free, sofit-normalized)
build_sample.py         build N dafs as a test sample
dictionaries/*.json     final per-tractate dictionaries, words in Gemara order
lookup/*.json           nikud-free lookup indexes, same shape as dictionaries
lookup/abbreviations.json  11,660 rashei tevot
lookup/master.json      28,148 keys, all tractates merged
docs/index.html         searchable web dictionary (GitHub Pages)
build_scan_data.py      builds docs/scan/<Tractate>.json for the scanner app (+ abbreviations,
                        + phrase meanings from phrases/<Tractate>.json)
phrases/<Tractate>.json per-spot phrase meanings (Berakhot: 2a–7a, 46a)
phrase_tasks.py         task sheets for writing phrase meanings; --check validates a part file
merge_phrases.py        merges phrases/parts/*.json into phrases/<Tractate>.json
docs/scan/              offline scanner test app (camera → OCR → find daf → tap word)
                        live at https://gemara-scanner.vercel.app — Vercel is connected
                        to this repo (root folder docs/scan): every push to main redeploys it; old copy at arielg613.github.io/Gemara-Pen/scan/
                        bump CACHE in docs/scan/sw.js AND CACHE_NAME in index.html whenever a file changes
```

**Gitignored build artifacts** — `word_contexts.json`, `real_dictionary.json`,
`unmatched.json`. These are large intermediates. They do not survive a
container restart, which is how Eruvin was lost.

---

## Formats

Dictionary (`dictionaries/Megillah.json`) — current target shape:

```json
{
  "tractate": "Megillah",
  "dafs": {
    "2a": [
      {"word": "מְגִילָּה", "translation": "Megilla", "lang": "aramaic", "pos": "name"}
    ]
  }
}
```

Lookup (`lookup/Megillah.json`) — same daf structure, but nikud stripped and
final letters normalized, flattened to a plain word→translation map:

```json
{"tractate": "Megillah", "dafs": {"2a": {"מגילה": "Megilla", "נקראת": "is read"}}}
```

`lang` is one of aramaic / hebrew / greek / persian / other.
`pos` is one of noun / verb / particle / pronoun / adjective / name.

---

## Things that bite

**Rate limits.** Long runs hit 429. `_call_with_backoff()` honors the
`retry-after` header and retries up to 6 times, and there is a 0.3s sleep
between batches. It still is not enough on a 10k-word tractate. Commit
partial progress rather than losing a run.

**Sofit normalization.** Lookup keys normalize ך→כ, ם→מ, ן→נ, ף→פ, ץ→צ. Both
`build_lookup_index.py` and `rebuild_ordered.py` do this. If only one of them
does it, words ending in final letters silently fail to match.

**Unknown words return `"?"`.** Deliberate — do not guess. `--fix-unmatched`
retries them with a stronger prompt.

**The website is one 4.1MB self-contained HTML file** at `docs/index.html`,
served from GitHub Pages at arielg613.github.io/gemara-pen. It has to be
regenerated after each new tractate to include it.

---

## Branches

Work goes to `main`. The branch `claude/gemara-pen-tractates-cbDu7` is stale —
it sits 19 commits behind `main` and predates the Sonnet pipeline, the lookup
indexes, and the web app. Do not build on it.


## 2026-11-07 — Berakhot complete, Sefaria-only
- All 125 dafs (2a–64a) lined up: 71,041 Hebrew words, 94.8% carry an exact piece of Sefaria's bold English, 5.2% "" (no literal counterpart; app shows "—").
- Two passes per daf: line-up agents, then review agents (lost negations, wrong-word pieces, fillable blanks). Every part file passes `phrase_tasks.py --check`.
- Source of truth: phrases/parts/Berakhot-<daf>.json → `merge_phrases.py Berakhot` → `build_scan_data.py Berakhot`.
- App: whole tractate, translation levels (Word/Phrase/Line/Full), hold ● = scan, menu "How to use". Cache v22.
- Known limits: Sefaria's bold order sometimes differs from the Hebrew, so some words stay blank; a piece can sit on a short word whose "not" lives in a neighbour only where no exact bold fix existed.
