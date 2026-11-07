#!/usr/bin/env python3
"""
Build docs/scan/KitzurYY.json for the scanner from kyy_tasks.py's source and
the word-group meanings in phrases/kyy/chNN.json (missing chapters get no chunks).

  {"book": "Kitzur Yalkut Yosef",
   "segs": [["YY Siman 4", hebrew, english, seif_label], ...],   # one per seif
   "chunks": {seg_index: [[n_words, meaning], ...]}}
"""
import json
import os
import sys

from kyy_tasks import chapters, words

segs, chunks = [], {}
for ch in chapters():
    path = f"phrases/kyy/{ch['key']}.json"
    part = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    if part is not None and len(part) != len(ch["seifim"]):
        sys.exit(f"{path}: {len(part)} seif lists, chapter has {len(ch['seifim'])}")
    for i, (n, he, en) in enumerate(ch["seifim"]):
        if part is not None:
            if sum(c[0] for c in part[i]) != len(words(he)):
                sys.exit(f"{path} seif {i}: word count mismatch")
            chunks[str(len(segs))] = part[i]
        segs.append(["YY " + ch["label"], he, en, n])
out = {"book": "Kitzur Yalkut Yosef", "segs": segs, "chunks": chunks}
with open("docs/scan/KitzurYY.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
print(f"docs/scan/KitzurYY.json: {len(segs)} seifim, {len(chunks)} with word meanings")
