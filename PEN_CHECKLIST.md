# Checklist: adding a masechet (or sefer) to the pen

Run this once per masechet. Anything marked **automatic** is built into the app and
applies to every book already on the pen — it never needs a new pass.

## A. Data passes (done once per masechet)
1. **Line up** Sefaria's bold English with the Hebrew words, daf by daf (`phrase_tasks.py`). English is copied, never written.
2. **Group words that belong together** as one unit: names, idioms (תא שמע), construct pairs (בעל הבית), "Rabbi X said".
3. **Flipped order:** when Sefaria's English order differs from the Hebrew, still use the piece (checker allows any order, each bold word used once).
4. **Review pass:** wrong word, lost negation ("not" must stay with its verb), fillable blanks.
5. **Checker passes** on every daf: exact Sefaria text, word counts match.
6. **Spot-read** a few dafs per helper; known spots (2a עמוד השחר = "dawn", 46a בעל הבית = "the host").
7. **Build, test, bump cache, push;** confirm live and "Ready offline".

For a non-Sefaria sefer (e.g. Kitzur Yalkut Yosef): Claude writes word groups in context, consistent with our translation, labelled AI; same grouping rule; `kyy_tasks.py --check`.

## B. Automatic display rules (in the app — no pass needed)
- **No "—" on screen:** a word with no English of its own joins its neighbour. את, קא, של, על, אל join the next word (את שמע = "Shema"); others join the phrase before. Scanning or stepping onto it shows the full group.
- **Capitals:** a piece shown alone gets a lowercase first letter if Sefaria writes that word lowercase mid-sentence ("Until" → "until", "The Rabbis" → "the Rabbis"); names keep capitals.
- **Neighbour preview:** under the word, the pieces before and after in gray ("from when · **one recite** · Shema").
- **Levels:** Word → Filled in (Sefaria's added words gray) → Sefaria. Yalkut Yosef: Word → Sentence → Whole seif. The chosen level stays while stepping.
- **Scan finds the book by itself:** all books are in one search index.

## C. Ariel's rules
- Gemara English = Sefaria only. Never Claude's own wording.
- Never edit the sefer's Hebrew; note defects instead.
- Fix things in the first perakim first; don't redo the whole masechet for each new idea — add it here instead.
