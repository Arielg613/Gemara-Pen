import requests
from flask import Flask, jsonify, render_template, request
from define import get_contextual_definition
from jastrow import lookup as jastrow_lookup
from translator import TRACTATES, search_word_in_daf, search_word_in_tractate

app = Flask(__name__)


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
    if tractate not in TRACTATES:
        return jsonify({"error": f"Unknown tractate: {tractate}"}), 400
    if amud not in ("a", "b"):
        return jsonify({"error": "Amud must be a or b."}), 400

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
    })


@app.route("/define", methods=["POST"])
def define():
    data = request.get_json()
    word    = (data.get("word")    or "").strip()
    aramaic = (data.get("aramaic") or "").strip()
    english = (data.get("english") or "").strip()

    if not word or not aramaic:
        return jsonify({"error": "Word and passage are required."}), 400

    try:
        definition = get_contextual_definition(word, aramaic, english)
        return jsonify({"definition": definition})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": f"AI error: {e}"}), 500


@app.route("/lookup", methods=["POST"])
def lookup():
    data = request.get_json()
    word = (data.get("word") or "").strip()

    if not word:
        return jsonify({"error": "Please enter a word."}), 400

    try:
        entries = jastrow_lookup(word)
        return jsonify({
            "word": word,
            "entries": entries,
            "found": len(entries) > 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
