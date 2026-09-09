# Author: Maharshi Soni | License: MIT
"""Local NLP engine for error classification and similarity analysis.

Provides two backends:

1. **sentence-transformers** (preferred): Uses the ``all-MiniLM-L6-v2`` model
   for high-quality semantic embeddings and cosine similarity.
2. **Built-in fallback**: A lightweight TF-IDF + cosine-similarity
   implementation that requires no external model downloads. Activates
   automatically when sentence-transformers is not installed.

Both backends expose the same public API, so the rest of the codebase is
agnostic to which one is active.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to load sentence-transformers; fall back to built-in TF-IDF
# ---------------------------------------------------------------------------

_ST_AVAILABLE = False
_model = None

try:
    from sentence_transformers import SentenceTransformer, util as st_util  # type: ignore

    _ST_AVAILABLE = True
    logger.debug("sentence-transformers is available.")
except ImportError:
    logger.debug(
        "sentence-transformers not installed; using built-in TF-IDF fallback."
    )


def _load_model() -> None:
    """Lazy-load the sentence-transformers model on first use.

    If loading fails (e.g. network error downloading weights, corrupt cache),
    the module transparently falls back to the built-in TF-IDF engine so the
    rest of the pipeline is never blocked by a transient model-loading issue.
    """
    global _model, _ST_AVAILABLE
    if _ST_AVAILABLE and _model is None:
        try:
            logger.info("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Model loaded.")
        except Exception as exc:
            logger.warning(
                "Failed to load sentence-transformers model (%s). "
                "Falling back to built-in TF-IDF engine.",
                exc,
            )
            _ST_AVAILABLE = False
            _model = None


# ---------------------------------------------------------------------------
# Built-in TF-IDF fallback
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _cosine_sim_vectors(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity between two sparse TF vectors."""
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _tf_vector(tokens: List[str]) -> Dict[str, float]:
    """Compute term-frequency vector from token list."""
    counts = Counter(tokens)
    total = len(tokens) if tokens else 1
    return {t: c / total for t, c in counts.items()}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_similarity(text_a: str, text_b: str) -> float:
    """Compute semantic similarity between two texts (0.0 to 1.0).

    Uses sentence-transformers when available, otherwise TF-IDF cosine.
    """
    if _ST_AVAILABLE:
        _load_model()
        embeddings = _model.encode([text_a, text_b], convert_to_tensor=True)
        score = st_util.cos_sim(embeddings[0], embeddings[1]).item()
        return max(0.0, min(1.0, score))

    # Fallback: TF-IDF cosine
    vec_a = _tf_vector(_tokenize(text_a))
    vec_b = _tf_vector(_tokenize(text_b))
    return round(_cosine_sim_vectors(vec_a, vec_b), 4)


def classify_error(error_message: str) -> Dict[str, object]:
    """Classify an error message into a category with confidence.

    Categories:
        - locator_not_found: A CSS/XPath selector failed to match.
        - text_mismatch: An assertion on element text failed.
        - timeout: The operation timed out.
        - network_error: A network-level failure occurred.
        - unknown: Could not classify.

    Returns a dict with ``category``, ``confidence``, and ``keywords``.
    """
    error_lower = error_message.lower()

    patterns: List[Tuple[str, List[str], float]] = [
        ("locator_not_found", ["locator not found", "selector", "element not found", "no such element"], 0.95),
        ("text_mismatch", ["text mismatch", "expected", "got", "assertion"], 0.90),
        ("timeout", ["timeout", "timed out", "deadline exceeded"], 0.92),
        ("network_error", ["network", "connection refused", "dns", "unreachable"], 0.88),
    ]

    best_category = "unknown"
    best_confidence = 0.0
    matched_keywords: List[str] = []

    for category, keywords, base_confidence in patterns:
        hits = [kw for kw in keywords if kw in error_lower]
        if hits:
            # Confidence increases slightly with more keyword matches
            confidence = min(1.0, base_confidence + 0.02 * (len(hits) - 1))
            if confidence > best_confidence:
                best_category = category
                best_confidence = confidence
                matched_keywords = hits

    if best_category == "unknown":
        best_confidence = 0.3

    return {
        "category": best_category,
        "confidence": round(best_confidence, 2),
        "keywords": matched_keywords,
    }


def find_most_similar(
    query: str, candidates: List[str], top_k: int = 3
) -> List[Tuple[str, float]]:
    """Find the top-k most similar strings to ``query`` from ``candidates``.

    Returns a list of (candidate, similarity_score) sorted by score descending.
    """
    if not candidates:
        return []

    scored = [(c, compute_similarity(query, c)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def extract_keywords(text: str, top_k: int = 5) -> List[str]:
    """Extract the most frequent meaningful tokens from text.

    Filters out very short tokens and common stop words.
    """
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "shall",
        "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "and",
        "but", "or", "nor", "not", "no", "so", "if", "then", "than",
        "that", "this", "it", "its",
    }
    tokens = _tokenize(text)
    filtered = [t for t in tokens if len(t) > 2 and t not in stop_words]
    counts = Counter(filtered)
    return [word for word, _ in counts.most_common(top_k)]


def is_nlp_model_available() -> bool:
    """Return whether the sentence-transformers model is available."""
    return _ST_AVAILABLE
