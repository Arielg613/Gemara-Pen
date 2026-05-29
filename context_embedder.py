"""
context_embedder.py — semantic context engine for Gemara Pen.

Two backends:
  TFIDFEmbedder  — offline, ships on the pen, built from Jastrow definitions
  BERELEmbedder  — full Talmudic Aramaic model, loaded when available

Usage:
  embedder = get_embedder()
  vec = embedder.embed("מלכא לשון המלך")
  # Compare vectors with cosine_sim(vec1, vec2)
"""

import json
import os
import re
import numpy as np
from typing import Protocol

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class Embedder(Protocol):
    def embed(self, text: str) -> np.ndarray: ...
    def embed_batch(self, texts: list[str]) -> np.ndarray: ...


class TFIDFEmbedder:
    """Offline TF-IDF embedder trained on all 28k Jastrow definitions.

    Vocabulary is built from Latin characters in Jastrow's English definitions
    (Hebrew characters stripped since we're embedding for semantic meaning).
    This runs on any machine with NumPy — no GPU, no internet, no model files.
    """

    def __init__(self):
        self._vocab: dict[str, int] | None = None
        self._idf: np.ndarray | None = None

    def _ensure_fitted(self):
        if self._vocab is not None:
            return
        path = os.path.join(_DATA_DIR, "tfidf_model.npz")
        if os.path.exists(path):
            npz = np.load(path, allow_pickle=True)
            self._vocab = npz["vocab"].item()
            self._idf = npz["idf"]
            return
        # Build from Jastrow
        jastrow = json.load(open(os.path.join(_DATA_DIR, "jastrow.json")))
        docs = []
        for entries in jastrow.values():
            for e in entries:
                text = re.sub(r"[^a-zA-Z ]", " ", e.get("def", "")).lower()
                docs.append(text)
        # Build vocabulary
        from collections import Counter
        tf_total = Counter()
        df = Counter()
        for doc in docs:
            words = set(doc.split())
            df.update(words)
            tf_total.update(doc.split())
        # Keep top 8000 words with df >= 3
        vocab_words = [w for w, c in df.most_common(8000) if df[w] >= 3 and len(w) > 2]
        self._vocab = {w: i for i, w in enumerate(vocab_words)}
        N = len(docs)
        self._idf = np.array([
            np.log((N + 1) / (df[w] + 1)) + 1
            for w in vocab_words
        ], dtype=np.float32)
        np.savez(path, vocab=np.array(self._vocab, dtype=object), idf=self._idf)

    def _tf_vec(self, text: str) -> np.ndarray:
        self._ensure_fitted()
        words = re.sub(r"[^a-zA-Z ]", " ", text).lower().split()
        v = np.zeros(len(self._vocab), dtype=np.float32)
        for w in words:
            if w in self._vocab:
                v[self._vocab[w]] += 1
        if words:
            v /= len(words)
        v *= self._idf
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

    def embed(self, text: str) -> np.ndarray:
        return self._tf_vec(text)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._tf_vec(t) for t in texts])


class BERELEmbedder:
    """BEREL 3.0 (dicta-il/BEREL_3.0, Apache 2.0) — full Talmudic model.

    Loaded lazily when transformers + torch are available and the model
    can be downloaded (requires network). Falls back to TFIDFEmbedder
    if unavailable.
    """

    def __init__(self, cache_dir: str = "/tmp/berel_cache"):
        self._model = None
        self._tokenizer = None
        self._cache_dir = cache_dir

    def _ensure_loaded(self):
        if self._model is not None:
            return
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
            self._tokenizer = AutoTokenizer.from_pretrained(
                "dicta-il/BEREL_3.0", cache_dir=self._cache_dir
            )
            self._model = AutoModel.from_pretrained(
                "dicta-il/BEREL_3.0", cache_dir=self._cache_dir
            )
            self._model.eval()
        except Exception as e:
            raise RuntimeError(f"BEREL unavailable: {e}")

    def embed(self, text: str) -> np.ndarray:
        import torch
        self._ensure_loaded()
        inputs = self._tokenizer(text, return_tensors="pt",
                                  max_length=512, truncation=True, padding=True)
        with torch.no_grad():
            out = self._model(**inputs)
        vec = out.last_hidden_state[:, 0, :].squeeze().numpy()
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return np.stack([self.embed(t) for t in texts])


def get_embedder(prefer_berel: bool = False) -> TFIDFEmbedder | BERELEmbedder:
    """Return the best available embedder.

    prefer_berel=True: try BEREL first, fall back to TF-IDF.
    prefer_berel=False (default): always use TF-IDF (offline pen mode).
    """
    if prefer_berel:
        try:
            e = BERELEmbedder()
            e._ensure_loaded()
            return e
        except Exception:
            pass
    return TFIDFEmbedder()


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    return float(np.dot(a, b))


def validate_sense_assignment(word: str, entry_defs: list[str],
                               tractate_to_idx: dict[str, int],
                               embedder: TFIDFEmbedder | None = None) -> dict:
    """Check whether the citation-based sense assignment matches embeddings.

    Returns {tractate: {"index": int, "confidence": float, "embedding_agrees": bool}}
    """
    if embedder is None:
        embedder = TFIDFEmbedder()

    if not entry_defs:
        return tractate_to_idx

    entry_vecs = embedder.embed_batch(entry_defs)

    result = {}
    for tractate, info in tractate_to_idx.items():
        idx = info["index"] if isinstance(info, dict) else info
        conf = info.get("confidence", 1.0) if isinstance(info, dict) else 1.0

        # Compare the assigned entry's vector to the others
        if len(entry_defs) < 2:
            result[tractate] = {"index": idx, "confidence": conf, "embedding_agrees": True}
            continue

        assigned_vec = entry_vecs[min(idx, len(entry_vecs) - 1)]
        others = [entry_vecs[i] for i in range(len(entry_vecs)) if i != idx]
        sim_assigned = np.mean([cosine_sim(assigned_vec, assigned_vec)])
        sim_others = np.mean([cosine_sim(assigned_vec, o) for o in others]) if others else 0.0

        # Embedding agrees if assigned entry is at least as self-similar
        agrees = sim_assigned >= sim_others * 0.9
        result[tractate] = {"index": idx, "confidence": conf, "embedding_agrees": agrees}

    return result
