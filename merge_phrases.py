#!/usr/bin/env python3
"""
Merge phrases/parts/<Tractate>-<daf>.json into phrases/<Tractate>.json.

Each part file is {daf: [segment chunk lists]} written by one helper. Dafs
already in phrases/<Tractate>.json are replaced by the part's version.
Afterwards run build_scan_data.py, which re-checks every word count.

Usage: python merge_phrases.py Berakhot
"""
import glob
import json
import re
import sys


def daf_key(d: str):
    m = re.match(r"(\d+)([ab])", d)
    return (int(m.group(1)), m.group(2)) if m else (9999, d)


def main():
    tractate = sys.argv[1]
    path = f"phrases/{tractate}.json"
    merged = json.load(open(path, encoding="utf-8"))
    for part in sorted(glob.glob(f"phrases/parts/{tractate}-*.json")):
        merged.update(json.load(open(part, encoding="utf-8")))
    about = {k: v for k, v in merged.items() if k.startswith("_")}
    dafs = sorted((k for k in merged if not k.startswith("_")), key=daf_key)
    out = {**about, **{d: merged[d] for d in dafs}}
    warn = []
    for d in dafs:
        for k, chunks in enumerate(out[d]):
            for n, g in chunks:
                if g.strip() == "?":
                    warn.append(f"{d} seg {k}: unknown ({n} words)")
                elif n > 6:
                    warn.append(f"{d} seg {k}: long chunk ({n} words) = {g}")
    # one line per segment keeps diffs readable
    lines = ["{"]
    items = list(out.items())
    for i, (k, v) in enumerate(items):
        end = "," if i < len(items) - 1 else ""
        if k.startswith("_"):
            lines.append(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}{end}")
            continue
        lines.append(f"  {json.dumps(k)}: [")
        for j, seg in enumerate(v):
            lines.append("    " + json.dumps(seg, ensure_ascii=False) + ("," if j < len(v) - 1 else ""))
        lines.append(f"  ]{end}")
    lines.append("}")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{path}: {len(dafs)} dafs ({', '.join(dafs)})")
    if warn:
        print("Check these:\n  " + "\n  ".join(warn))


if __name__ == "__main__":
    main()
