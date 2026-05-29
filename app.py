"""
Gemara Pen — web layer (online phone-test harness + REST API).

This wraps the offline BRAIN (jastrow.py) in a Flask API and serves the
web UI. The Sefaria passage search (translator.py) lives here too and DOES
need internet. The dictionary lookup itself does not.

Endpoints:
  GET  /                  the web UI
  POST /lookup            dictionary lookup (the brain)        {word}
  POST /translate         passage search via Sefaria           {word, tractate, daf, amud}
  POST /precache          warm the tractate cache (background)
  GET  /precache/status   progress of /precache
"""

import threading
from flask import Flask, jsonify, render_template, request
from jastrow import analyze as jastrow_analyze, expand_abbreviation, lookup_phrase
from translator import TRACTATES, _load_tractate, search_word_in_daf, search_word_in_tractate, search_word_in_all_tractates

app = Flask(__name__)

_precache_state = {"status": "idle", "loaded": 0, "total": 0, "errors": []}
_precache_lock  = threading.Lock()


def _run_precache():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    names = sorted(TRACTATES.keys())
    with _precache_lock:
        _precache_state.update({"status": "running", "loaded": 0, "total": len(names), "errors": []})

    loaded = 0
    errors = []

    def _load_one(name):
        try:
            _load_tractate(name)
            return name, None
        except Exception as e:
            return name, str(e)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_load_one, n): n for n in names}
        for fut in as_completed(futures):
            name, err = fut.result()
            loaded += 1
            if err:
                errors.append(name)
            with _precache_lock:
                _precache_state["loaded"] = loaded

    with _precache_lock:
        _precache_state["status"] = "done"
        _precache_state["errors"] = errors


@app.route("/")
def index():
    max_daf = {name: info["max_daf"] for name, info in TRACTATES.items()}
    return render_template(
        "index.html",
        tractates=sorted(TRACTATES.keys()),
        tractate_max_daf=max_daf,
    )


@app.route("/translate", methods=["POST"])
def translate():
    data = request.get_json()
    word = (data.get("word") or "").strip()
    tractate = (data.get("tractate") or "").strip()
    daf = str(data.get("daf", "")).strip()
    amud = data.get("amud", "a")

    if not word:
        return jsonify({"error": "Please enter a word."}), 400
    if amud not in ("a", "b"):
        return jsonify({"error": "Amud must be a or b."}), 400

    # "all" means search every tractate
    if tractate == "all":
        try:
            results = search_word_in_all_tractates(word)
        except Exception as e:
            return jsonify({"error": f"Sefaria error: {e}"}), 502
        return jsonify({
            "word": word,
            "tractate": "All Tractates",
            "daf": "",
            "results": results,
            "total": len(results),
            "all_tractates": True,
        })

    if tractate not in TRACTATES:
        return jsonify({"error": f"Unknown tractate: {tractate}"}), 400

    try:
        if daf:
            results = search_word_in_daf(word, tractate, daf, amud)
            location = f"{daf}{amud}"
        else:
            results = search_word_in_tractate(word, tractate)
            location = "all daf"
    except Exception as e:
        return jsonify({"error": f"Sefaria error: {e}"}), 502

    return jsonify({
        "word": word,
        "tractate": tractate,
        "daf": location,
        "results": results,
        "total": len(results),
        "all_tractates": False,
    })


@app.route("/lookup", methods=["POST"])
def lookup():
    data = request.get_json()
    word     = (data.get("word")     or "").strip()
    tractate = (data.get("tractate") or "").strip()

    if not word:
        return jsonify({"error": "Please enter a word."}), 400

    try:
        # 1. Check for abbreviation (ת"ל, ק"ו, etc.)
        abbrev = expand_abbreviation(word)
        if abbrev:
            return jsonify({
                "word":    word,
                "type":    "abbreviation",
                "found":   True,
                "gloss":   abbrev["en"],
                "full":    abbrev.get("full", ""),
                "entries": [],
            })

        # 2. Check for known Talmudic phrase (תא שמע, פשיטא, etc.)
        phrase = lookup_phrase(word)
        if phrase:
            return jsonify({
                "word":    word,
                "type":    "phrase",
                "found":   True,
                "gloss":   phrase["meaning"],
                "entries": [],
            })

        # 3. Dictionary lookup (with optional tractate context)
        result = jastrow_analyze(word, tractate)
        resp = {
            "word":          word,
            "type":          "word",
            "found":         result["found"],
            "match_type":    result["match_type"],
            "gloss":         result.get("gloss", ""),
            "context_sense": result.get("context_sense", False),
            "tractate":      tractate,
            "entries":       result["entries"],
        }
        if result.get("morphology"):
            resp["morphology"] = result["morphology"]
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/precache", methods=["POST"])
def precache():
    with _precache_lock:
        if _precache_state["status"] == "running":
            return jsonify({"started": False, "already_running": True})
    t = threading.Thread(target=_run_precache, daemon=True)
    t.start()
    return jsonify({"started": True, "total": len(TRACTATES)})


@app.route("/precache/status", methods=["GET"])
def precache_status():
    with _precache_lock:
        return jsonify(dict(_precache_state))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
