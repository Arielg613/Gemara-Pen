"""
Gemara Pen — web layer (online phone-test harness + REST API).

This wraps the offline BRAIN (jastrow.py) in a Flask API and serves the
web UI. The Sefaria passage search (translator.py) lives here too and DOES
need internet. The dictionary lookup itself does not.

Endpoints:
  GET  /                  the web UI
  POST /lookup            dictionary lookup (the brain)        {word, tractate?}
  POST /translate         passage search via Sefaria           {word, tractate, daf, amud}
  POST /ocr               Rashi-script OCR (base64 image)      {image_b64, lang?}
  POST /precache          warm the tractate cache (background)
  GET  /precache/status   progress of /precache
"""

import base64
import io
import os
import threading
from flask import Flask, jsonify, render_template, request
from jastrow import analyze as jastrow_analyze, expand_abbreviation, lookup_phrase
from translator import TRACTATES, _load_tractate, search_word_in_daf, search_word_in_tractate, search_word_in_all_tractates

# Optional: Rashi-script OCR via pytesseract + tessdata
_TESSDATA_DIR = os.path.join(os.path.dirname(__file__), "data")
try:
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

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
            "passages":      [],
        }
        if result.get("morphology"):
            resp["morphology"] = result["morphology"]

        # 4. When tractate is set, also fetch passages from Sefaria (shows
        #    the word in the actual text the user is studying)
        if tractate and tractate in TRACTATES:
            try:
                passages = search_word_in_tractate(word, tractate)
                resp["passages"] = passages[:5]   # cap at 5 to keep response fast
            except Exception:
                pass   # Sefaria unavailable — degrade gracefully

        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ocr", methods=["POST"])
def ocr():
    """Rashi-script (or square-script) OCR from a base64-encoded image.

    Request JSON:
      image_b64  — base64-encoded image (JPEG/PNG)
      lang       — tesseract language: "heb_rashi" (default) or "heb_rashi_fast"

    Returns {text, words, lang} or {error}.
    """
    if not _OCR_AVAILABLE:
        return jsonify({"error": "OCR not available on this server (pytesseract not installed)"}), 503

    data = request.get_json()
    image_b64 = (data.get("image_b64") or "").strip()
    lang = data.get("lang", "heb_rashi")

    if lang not in ("heb_rashi", "heb_rashi_fast"):
        lang = "heb_rashi"

    if not image_b64:
        return jsonify({"error": "No image provided."}), 400

    try:
        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("L")  # greyscale

        # Point tesseract at our bundled tessdata
        cfg = f"--tessdata-dir {_TESSDATA_DIR} --psm 6"
        text = pytesseract.image_to_string(img, lang=lang, config=cfg).strip()

        # Strip non-Hebrew garbage characters that tesseract sometimes emits
        import re
        words = [w for w in re.sub(r'[^א-תװ-״\s]', ' ', text).split()
                 if len(w) >= 2]

        return jsonify({"text": text, "words": words, "lang": lang})
    except Exception as e:
        return jsonify({"error": f"OCR failed: {e}"}), 500


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
