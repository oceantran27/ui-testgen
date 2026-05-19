from __future__ import annotations

import hashlib
import re
import unicodedata


_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PUNCT_STRIP = str.maketrans("", "", '.,:;!?"\'`()')


def slug_text(value: str) -> str:
    s = value.lower().strip()
    s = s.replace("\\", "/")
    s = _NON_ALNUM.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "x"


def short_hash(value: str, n_chars: int = 8) -> str:
    h = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return h[:n_chars]


def normalize_for_match(value: str) -> str:
    """Lowercase, trim, collapse whitespace, strip simple punctuation; keep Vietnamese diacritics."""
    s = unicodedata.normalize("NFKC", value)
    s = s.lower().strip().translate(_PUNCT_STRIP)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def text_matches(text_a: str, text_b: str) -> bool:
    """True if normalized a contains b or b contains a (spec §7)."""
    na = normalize_for_match(text_a)
    nb = normalize_for_match(text_b)
    if not na or not nb:
        return na == nb
    return na in nb or nb in na


def normalized_join_contains(haystack: str, needle: str) -> bool:
    """Whether normalized needle is contained in normalized haystack (one-way)."""
    h = normalize_for_match(haystack)
    n = normalize_for_match(needle)
    if not n:
        return True
    return n in h
