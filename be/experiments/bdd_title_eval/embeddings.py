from __future__ import annotations

import numpy as np

_DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"


def load_model(model_name: str = _DEFAULT_MODEL, device: str | None = None):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


def encode_normalized(model, texts: list[str]) -> "NDArray[np.floating]":
    """L2-normalized embeddings; dot product equals cosine similarity."""
    if not texts:
        return np.zeros((0, 1), dtype=np.float32)
    emb = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return np.asarray(emb, dtype=np.float32)
