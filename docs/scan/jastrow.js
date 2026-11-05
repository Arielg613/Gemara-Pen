/*
 * Offline Jastrow lookup for the Gemara scanner.
 *
 *   await Jastrow.load("jastrow.json");
 *   Jastrow.lookup("דְּתַנְיָא")  ->  [{head, def, gloss, via, key}, ...]  (max 3)
 *
 * Data comes from build_jastrow_data.py (repo root). The candidate generation
 * and ranking below MUST stay identical to candidates()/resolve() there —
 * the build keeps only the entries this code can reach for Berakhot words.
 * Plain browser script: no modules, no dependencies.
 */
(function (global) {
  "use strict";

  var MAX_RESULTS = 3;
  var TO_FINAL = { "מ": "ם", "נ": "ן", "פ": "ף", "כ": "ך", "צ": "ץ" };
  var FROM_FINAL = { "ם": "מ", "ן": "נ", "ף": "פ", "ך": "כ", "ץ": "צ" };

  var PREFIXES = ["אית", "את", "מת", "הת", "נת",
    "ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
    "א", "י", "נ", "ת", "ק", "תי"];
  var SUFFIXES = ["ייתא",
    "תון", "תין", "נון", "נין",
    "יות", "יין", "יהם", "יהן", "יכם", "יכן",
    "הון", "הין", "כון", "כין",
    "תם", "תן",
    "תו", "תה", "תך",
    "יה", "יו", "יך", "יי",
    "הם", "הן", "כם", "כן",
    "נא", "נו", "תי",
    "ות", "ין", "ון", "ית",
    "תא", "את",
    "ים", "יא", "נן",
    "א", "ה", "ת", "ן", "י", "ו", "ך"];
  var SAFE_PREFIXES = ["ו", "ב", "ל", "כ", "מ", "ה", "ד", "ש",
    "א", "י", "נ", "ת", "ק",
    "אית", "את", "מת", "הת", "נת"];
  var PREP = "ובלכמהדש";
  var GROUP_ORDER = { suf: 0, pre: 1, ext: 2 };
  var VAV_COST = 0.5, EXT_COST = 1.5;

  var data = null;      // {e: {key: rows}, q: {key: gloss}}
  var loading = null;

  function finalize(s) {
    var c = s.charAt(s.length - 1);
    return TO_FINAL[c] ? s.slice(0, -1) + TO_FINAL[c] : s;
  }

  // Consonants only; interior finals made regular, last letter made final.
  function norm(word) {
    var w = String(word || "").replace(/[^א-ת]/g, "");
    if (!w) return "";
    var head = "";
    for (var i = 0; i < w.length - 1; i++) head += FROM_FINAL[w[i]] || w[i];
    return finalize(head + w[w.length - 1]);
  }

  function prefixCost(p) {
    for (var i = 0; i < p.length; i++) if (PREP.indexOf(p[i]) < 0) return p.length + 0.5;
    return p.length;
  }
  function suffixCost(s) { return s.length + (s.length === 1 ? 0.5 : 0); }
  function op(kind, text, cost) { return { k: kind, t: text, c: cost }; }
  function starts(s, p) { return s.slice(0, p.length) === p; }
  function ends(s, p) { return s.length >= p.length && s.slice(s.length - p.length) === p; }

  // Mirror of candidates() in build_jastrow_data.py. Returns best-first list of
  // {cand, cost, group, ops}; the exact word itself is not included.
  function candidates(word) {
    var best = new Map();

    function add(stem, group, ops) {
      if (stem.length < 2) return;
      var cost = 0;
      for (var i = 0; i < ops.length; i++) cost += ops[i].c;
      [stem, finalize(stem)].forEach(function (c) {
        if (c === word) return;
        var g = GROUP_ORDER[group], cur = best.get(c);
        if (!cur || cost < cur.cost || (cost === cur.cost && g < GROUP_ORDER[cur.group])) {
          best.set(c, { cand: c, cost: cost, group: group, ops: ops });
        }
      });
    }

    var bases = [[word, []]];
    if (word.length >= 3 && word[1] === "ו") {
      bases.push([word[0] + word.slice(2), [op("v", "ו", VAV_COST)]]);
    }
    if (starts(word, "ו") && word.length >= 4) {
      var inner = word.slice(1);
      bases.push([inner, [op("p", "ו", 1)]]);
      if (inner.length >= 3 && inner[1] === "ו") {
        bases.push([inner[0] + inner.slice(2), [op("p", "ו", 1), op("v", "ו", VAV_COST)]]);
      }
    }
    for (var b = 1; b < bases.length; b++) add(bases[b][0], "pre", bases[b][1]);

    var first = [];
    function pushWithPrefixes(stem, group, ops) {
      first.push([stem, group, ops]);
      PREFIXES.forEach(function (pfx) {
        if (starts(stem, pfx) && stem.length - pfx.length >= 2) {
          first.push([stem.slice(pfx.length), group, ops.concat([op("p", pfx, prefixCost(pfx))])]);
        }
      });
    }
    bases.forEach(function (bo) {
      var base = bo[0], bops = bo[1];
      SUFFIXES.forEach(function (sfx) {
        if (ends(base, sfx) && base.length - sfx.length >= 2) {
          var stem = base.slice(0, base.length - sfx.length);
          var sops = bops.concat([op("s", sfx, suffixCost(sfx))]);
          pushWithPrefixes(stem, "suf", sops);
          if (stem.length >= 3 && stem[1] === "ו") {
            pushWithPrefixes(stem[0] + stem.slice(2), "suf", sops.concat([op("v", "ו", VAV_COST)]));
          }
          if (stem.length >= 4) {
            [2, 3].forEach(function (vpos) {
              if (vpos < stem.length && stem[vpos] === "ו") {
                pushWithPrefixes(stem.slice(0, vpos) + stem.slice(vpos + 1), "suf",
                  sops.concat([op("v", "ו", VAV_COST)]));
              }
            });
          }
        }
      });
      PREFIXES.forEach(function (pfx) {
        if (starts(base, pfx) && base.length - pfx.length >= 2) {
          var st = base.slice(pfx.length);
          var pops = bops.concat([op("p", pfx, prefixCost(pfx))]);
          first.push([st, "pre", pops]);
          if (st.length >= 3 && st[1] === "ו") {
            first.push([st[0] + st.slice(2), "pre", pops.concat([op("v", "ו", VAV_COST)])]);
          }
        }
      });
    });

    first.forEach(function (f) { add(f[0], f[1], f[2]); });
    var second = first.concat(bases.slice(1).map(function (bo) { return [bo[0], "pre", bo[1]]; }));
    second.forEach(function (f) {
      SAFE_PREFIXES.forEach(function (pfx) {
        if (starts(f[0], pfx) && f[0].length - pfx.length >= 2) {
          add(f[0].slice(pfx.length), "pre", f[2].concat([op("p", pfx, prefixCost(pfx))]));
        }
      });
    });
    Array.from(best.values()).forEach(function (v) {
      ["ה", "א"].forEach(function (sfx) {
        var c = v.cand;
        if (ends(c, sfx)) return;
        var last = c[c.length - 1];
        var x = (FROM_FINAL[last] ? c.slice(0, -1) + FROM_FINAL[last] : c) + sfx;
        if (x !== word && !best.has(x)) {
          best.set(x, { cand: x, cost: v.cost + EXT_COST, group: "ext",
            ops: v.ops.concat([op("x", sfx, 0)]) });
        }
      });
    });

    var out = Array.from(best.values());
    out.sort(function (a, b) {
      return (a.cost - b.cost) ||
        (GROUP_ORDER[a.group] - GROUP_ORDER[b.group]) ||
        (b.cand.length - a.cand.length) ||
        (a.cand < b.cand ? -1 : a.cand > b.cand ? 1 : 0);
    });
    return out;
  }

  function describe(ops) {
    var parts = [];
    ops.forEach(function (o) {
      if (o.k === "p") parts.push("prefix " + o.t + "־ removed");
      else if (o.k === "s") parts.push("suffix ־" + o.t + " removed");
      else if (o.k === "v") parts.push("vowel-letter ו dropped");
      else if (o.k === "x") parts.push("ending ־" + o.t + " added");
    });
    return parts.join(", ");
  }

  function plain(s) {
    return String(s || "").replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
  }

  function rowResult(key, row, via) {
    var def = plain(row[2]);
    var gloss = typeof row[1] === "number" ? def.slice(0, row[1]) : plain(row[1]);
    return { head: row[0], def: def || gloss, gloss: gloss, via: via, key: key };
  }

  function lookup(word) {
    if (!data) return [];
    var results = [];
    var raw = String(word || "").trim();

    // Hand-written glosses for common Talmudic terms (exact form only)
    var qkey = raw.split(/[\s־]+/).map(norm).filter(Boolean).join(" ");
    if (qkey && data.q[qkey]) {
      results.push({ head: qkey, def: data.q[qkey], gloss: data.q[qkey],
        via: "common Talmudic term", key: qkey });
    }
    var w = norm(raw);
    if (w.length < 2) return results;

    // Mirror of resolve() in build_jastrow_data.py.
    // Pass 1: only entries with a real gloss (a cross-ref counts if its target
    // has one), best candidate first. Pass 2: fill remaining slots with the rest.
    // A cross-ref contributes one entry: the first not-yet-shown target entry.
    var cands = [{ cand: w, cost: 0, group: "exact", ops: [] }].concat(candidates(w))
      .filter(function (c) { return !!data.e[c.cand]; });
    var seen = {}, found = 0;
    function sig(row) { return row[0] + "\u0000" + (row[2] || row[1]); }
    function hasGloss(row) { return !!row[1]; }

    for (var pass = 0; pass < 2; pass++) {
      var needGloss = pass === 0;
      for (var i = 0; i < cands.length; i++) {
        var c = cands[i], rows = data.e[c.cand], via = describe(c.ops);
        for (var r = 0; r < rows.length; r++) {
          if (found >= MAX_RESULTS) return results.slice(0, MAX_RESULTS);
          var row = rows[r];
          if (row.length > 3 && data.e[row[3]]) {
            var trs = data.e[row[3]];
            for (var j = 0; j < trs.length; j++) {
              var tr = trs[j];
              if (seen[sig(tr)] || tr.length > 3) continue;
              if (needGloss && !hasGloss(tr)) break;
              seen[sig(tr)] = true;
              found++;
              var note = "see " + row[3] + " (from " + row[0] + ")";
              results.push(rowResult(row[3], tr, via ? via + "; " + note : note));
              break;
            }
            continue;
          }
          if (row.length > 3 || hasGloss(row) !== needGloss || seen[sig(row)]) continue;
          seen[sig(row)] = true;
          found++;
          results.push(rowResult(c.cand, row, via));
        }
      }
    }
    return results.slice(0, MAX_RESULTS);
  }

  function load(url) {
    if (data) return Promise.resolve(api);
    if (loading) return loading;
    loading = fetch(url || "jastrow.json")
      .then(function (r) {
        if (!r.ok) throw new Error("Jastrow: HTTP " + r.status);
        return r.json();
      })
      .then(function (json) { setData(json); return api; })
      .catch(function (err) { loading = null; throw err; });
    return loading;
  }

  function setData(json) {
    data = { e: (json && json.e) || {}, q: (json && json.q) || {} };
  }

  var api = {
    load: load,
    lookup: lookup,
    isLoaded: function () { return !!data; },
    // for tests / tooling
    _setData: setData,
    _candidates: candidates,
    _norm: norm
  };
  global.Jastrow = api;
})(typeof window !== "undefined" ? window : this);
