"""Near-duplicate UI screenshots via CLIP (ViT-B/32) embeddings and ChromaDB vector storage."""

from __future__ import annotations

import hashlib
import io
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable

import chromadb
import numpy as np
from chromadb.config import Settings
from PIL import Image
import torch
from transformers import CLIPModel, CLIPProcessor

from app.core.config import settings

logger = logging.getLogger(__name__)

_CLIP_MODEL: CLIPModel | None = None
_CLIP_PROCESSOR: CLIPProcessor | None = None
_CLIP_DEVICE: str | None = None
_CLIP_LOCK = threading.Lock()


def _ensure_rgb(pil: Image.Image) -> Image.Image:
    if pil.mode in ("RGB", "L"):
        if pil.mode == "L":
            return pil.convert("RGB")
        return pil
    if pil.mode in ("RGBA", "P", "PA"):
        if pil.mode in ("P", "PA"):
            pil = pil.convert("RGBA")
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[-1] if pil.mode == "RGBA" else None)
        return bg
    return pil.convert("RGB")


def _normalized_png_bytes(pil: Image.Image) -> bytes:
    """Deterministic PNG bytes for content hashing."""
    rgb = _ensure_rgb(pil)
    buf = io.BytesIO()
    rgb.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def content_image_id(pil: Image.Image) -> str:
    """Stable sha256 hex id from normalized PNG bytes."""
    return hashlib.sha256(_normalized_png_bytes(pil)).hexdigest()


def _clip_device() -> str:
    if settings.STATE_GRAPH_CLIP_DEVICE:
        return settings.STATE_GRAPH_CLIP_DEVICE
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _get_clip() -> tuple[CLIPModel, CLIPProcessor, str]:
    global _CLIP_MODEL, _CLIP_PROCESSOR, _CLIP_DEVICE
    with _CLIP_LOCK:
        if _CLIP_MODEL is not None and _CLIP_PROCESSOR is not None and _CLIP_DEVICE is not None:
            return _CLIP_MODEL, _CLIP_PROCESSOR, _CLIP_DEVICE
        model_id = settings.STATE_GRAPH_CLIP_MODEL_ID
        device = _clip_device()
        logger.info("Loading CLIP for dedup: %s on %s", model_id, device)
        proc = CLIPProcessor.from_pretrained(model_id)
        model = CLIPModel.from_pretrained(model_id)
        model = model.to(device)
        model.eval()
        _CLIP_MODEL = model
        _CLIP_PROCESSOR = proc
        _CLIP_DEVICE = device
        return model, proc, device


def encode_image_clip(pil: Image.Image) -> np.ndarray:
    """L2-normalized CLIP image embedding (float32 1D vector)."""
    model, processor, device = _get_clip()
    rgb = _ensure_rgb(pil)
    inputs = processor(images=rgb, return_tensors="pt")
    pixel_values = inputs["pixel_values"].to(device)
    with torch.no_grad():
        # Use vision tower + projection explicitly. Some Transformers / input dict
        # combinations make get_image_features return ModelOutput instead of a tensor.
        vision_out = model.vision_model(pixel_values=pixel_values)
        pooled = vision_out.pooler_output
        if pooled is None:
            pooled = vision_out.last_hidden_state[:, 0, :]
        feats = model.visual_projection(pooled)
    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.detach().cpu().numpy().astype(np.float32).reshape(-1)


@dataclass
class DedupResult:
    """Canonical screens and mapping from every input path to canonical image_id."""

    canonical_paths: list[str] = field(default_factory=list)
    canonical_image_ids: list[str] = field(default_factory=list)
    input_path_to_image_id: dict[str, str] = field(default_factory=dict)
    dropped_paths: list[str] = field(default_factory=list)
    dropped_to_canonical_path: dict[str, str] = field(default_factory=dict)
    dropped_match_reason: dict[str, str] = field(default_factory=dict)
    dropped_metrics: dict[str, dict[str, float]] = field(default_factory=dict)


def dedupe_image_paths(
    paths: list[str],
    *,
    cosine_threshold: float | None = None,
    encode_fn: Callable[[Image.Image], np.ndarray] | None = None,
) -> DedupResult:
    """
    Greedy deduplication: first path is canonical; later paths whose CLIP embedding
    has cosine similarity > threshold to any stored canonical are dropped.

    ``encode_fn`` is optional (for tests); default uses ViT-B/32 CLIP and caches the model.
    """
    if not paths:
        return DedupResult()

    threshold = (
        cosine_threshold
        if cosine_threshold is not None
        else settings.STATE_GRAPH_IMAGE_DEDUP_COSINE_THRESHOLD
    )
    encoder = encode_fn or encode_image_clip

    client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
    collection = client.create_collection(
        name=f"ui_dedup_{uuid.uuid4().hex}",
        metadata={"hnsw:space": "cosine"},
    )

    result = DedupResult()

    for p in paths:
        try:
            pil = Image.open(p)
            pil.load()
            pil = pil.copy()
        except Exception as exc:
            logger.error("dedupe: failed to open %s: %s", p, exc)
            raise

        try:
            cid = content_image_id(pil)
            emb = encoder(pil)
        finally:
            pil.close()

        emb = emb.astype(np.float32, copy=False)
        norm = float(np.linalg.norm(emb))
        if norm > 1e-12:
            emb = emb / norm

        matched_canon_path: str | None = None
        matched_image_id: str | None = None
        best_sim = -1.0

        if collection.count() > 0:
            stored = collection.get(include=["embeddings", "metadatas"])
            raw_embs = stored.get("embeddings")
            metas = stored.get("metadatas") or []
            emb_rows: list[np.ndarray] = []
            if raw_embs is not None:
                arr = np.asarray(raw_embs, dtype=np.float32)
                if arr.ndim == 1:
                    emb_rows = [arr]
                elif arr.ndim == 2:
                    emb_rows = [arr[i] for i in range(arr.shape[0])]
            for vec, meta in zip(emb_rows, metas):
                if vec is None or meta is None:
                    continue
                v = np.asarray(vec, dtype=np.float32)
                vn = float(np.linalg.norm(v))
                if vn > 1e-12:
                    v = v / vn
                sim = float(np.dot(emb, v))
                if sim > best_sim:
                    best_sim = sim
                    matched_canon_path = meta.get("canonical_path")
                    matched_image_id = meta.get("image_id")

        if matched_canon_path and matched_image_id and best_sim > threshold:
            result.input_path_to_image_id[p] = matched_image_id
            result.dropped_paths.append(p)
            result.dropped_to_canonical_path[p] = matched_canon_path
            result.dropped_match_reason[p] = "clip_cosine"
            result.dropped_metrics[p] = {"cosine_similarity": best_sim}
            continue

        chroma_id = f"c_{len(result.canonical_paths)}"
        collection.add(
            ids=[chroma_id],
            embeddings=[emb.tolist()],
            metadatas=[{"canonical_path": p, "image_id": cid}],
        )
        result.canonical_paths.append(p)
        result.canonical_image_ids.append(cid)
        result.input_path_to_image_id[p] = cid

    return result
