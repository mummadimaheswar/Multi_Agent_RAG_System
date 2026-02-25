from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

log = logging.getLogger("agents.rag")


@dataclass
class RankedChunk:
    url: str
    title: str | None
    text: str
    score: float


# ── Model caching (singleton) ────────────────────────────────
@lru_cache(maxsize=1)
def _get_bi_encoder():
    """Lazy-load and cache the bi-encoder model (loaded once, reused)."""
    from sentence_transformers import SentenceTransformer  # type: ignore
    log.info("Loading bi-encoder model (one-time)…")
    return SentenceTransformer("all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _get_cross_encoder():
    """Lazy-load and cache the cross-encoder model (loaded once, reused)."""
    from sentence_transformers import CrossEncoder  # type: ignore
    log.info("Loading cross-encoder model (one-time)…")
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def _chunk_text(text: str, *, max_chars: int = 900) -> list[str]:
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end])
        start = end
    return chunks


def _bi_encoder_rank(query: str, chunks: list[tuple[str, str | None, str]], top_k: int) -> list[RankedChunk]:
    """Stage 1 — bi-encoder (SentenceTransformer) ranking."""
    model = _get_bi_encoder()
    query_vec = model.encode([query], normalize_embeddings=True)
    text_vecs = model.encode([c[2] for c in chunks], normalize_embeddings=True)
    scores = (text_vecs @ query_vec[0]).tolist()
    ranked = sorted(
        [RankedChunk(url=u, title=t, text=tx, score=float(s)) for (u, t, tx), s in zip(chunks, scores)],
        key=lambda x: x.score,
        reverse=True,
    )
    return ranked[:top_k]


def _cross_encoder_rerank(query: str, candidates: list[RankedChunk], top_k: int) -> list[RankedChunk]:
    """Stage 2 — cross-encoder reranking for higher precision (DL technique)."""
    try:
        reranker = _get_cross_encoder()
        pairs = [(query, c.text) for c in candidates]
        scores = reranker.predict(pairs).tolist()
        for c, s in zip(candidates, scores):
            c.score = float(s)
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:top_k]
    except Exception:
        # Cross-encoder not installed — keep bi-encoder order
        return candidates[:top_k]


def _tfidf_rank(query: str, chunks: list[tuple[str, str | None, str]], top_k: int) -> list[RankedChunk]:
    """Fallback — TF-IDF + cosine similarity (no DL required)."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
    X = vectorizer.fit_transform([c[2] for c in chunks])
    q = vectorizer.transform([query])
    sims = cosine_similarity(X, q).reshape(-1)
    ranked = sorted(
        [RankedChunk(url=u, title=t, text=tx, score=float(s)) for (u, t, tx), s in zip(chunks, sims)],
        key=lambda x: x.score,
        reverse=True,
    )
    return ranked[:top_k]


def rank_chunks(query: str, docs: list[dict], *, top_k: int = 12) -> list[RankedChunk]:
    """Two-stage ranking pipeline:
       1) Bi-encoder (DL) or TF-IDF fallback for initial retrieval.
       2) Cross-encoder (DL) reranking for precision.
    """

    chunks: list[tuple[str, str | None, str]] = []
    for doc in docs:
        url = doc.get("url", "")
        title = doc.get("title")
        for ch in _chunk_text(doc.get("text", "")):
            chunks.append((url, title, ch))

    if not chunks:
        return []

    # Stage 1 — initial retrieval (wider net: 3x top_k)
    try:
        candidates = _bi_encoder_rank(query, chunks, top_k=min(len(chunks), top_k * 3))
    except Exception:
        candidates = _tfidf_rank(query, chunks, top_k=min(len(chunks), top_k * 3))

    # Stage 2 — cross-encoder reranking (precision)
    return _cross_encoder_rerank(query, candidates, top_k)
