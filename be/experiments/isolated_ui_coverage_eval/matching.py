"""Normalize strings, extract Gherkin quotes, and one-to-one match to ground-truth labels."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

# Lines whose first Gherkin keyword is When or And (case-insensitive).
_WHEN_AND_LINE = re.compile(
    r"^\s*(When|And)\b",
    re.IGNORECASE,
)
_DOUBLE_QUOTED = re.compile(r'"([^"]*)"')

_NON_ALNUM_SPACES = re.compile(r"[^a-z0-9\s]+", re.IGNORECASE)


def normalize_for_match(label: str) -> str:
    s = label.strip().lower()
    s = _NON_ALNUM_SPACES.sub(" ", s)
    return " ".join(s.split())


def string_similarity(a: str, b: str) -> float:
    na, nb = normalize_for_match(a), normalize_for_match(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def extract_quoted_spans_from_when_and_lines(gherkin_text: str) -> list[str]:
    """Double-quoted substrings only from lines that start with When/And.

    Order-preserving **distinct** list: same quote text only appears once (comparison
    uses casefold so ``Login`` and ``login`` count as one; first spelling kept).
    """
    out: list[str] = []
    seen_casefold: set[str] = set()
    for line in gherkin_text.splitlines():
        if not _WHEN_AND_LINE.match(line):
            continue
        for m in _DOUBLE_QUOTED.finditer(line):
            inner = m.group(1).strip()
            if not inner:
                continue
            key = inner.casefold()
            if key in seen_casefold:
                continue
            seen_casefold.add(key)
            out.append(inner)
    return out


def strip_markdown_code_fence(text: str) -> str:
    """Remove outer ``` or ```lang ... ``` wrapper if present."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    nl = s.find("\n")
    if nl == -1:
        return s
    body = s[nl + 1 :]
    end = body.rfind("```")
    if end != -1:
        body = body[:end]
    return body.strip()


def _flatten_user_intents_gherkin_json(blob: str) -> str | None:
    """
    If ``blob`` is JSON with top-level ``user_intents`` and string ``gherkin`` fields,
    return those Gherkin blocks joined (newlines preserved inside each block).
    """
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    ui = data.get("user_intents")
    if not isinstance(ui, list):
        return None
    parts: list[str] = []
    for item in ui:
        if not isinstance(item, dict):
            continue
        g = item.get("gherkin")
        if isinstance(g, str) and g.strip():
            parts.append(g)
    if not parts:
        return None
    return "\n\n".join(parts)


def normalize_baseline_model_output_for_quotes(raw: str) -> str:
    """
    Vision models often ignore \"plain Gherkin only\" and return markdown-wrapped JSON
    with Gherkin embedded in ``user_intents[].gherkin``. Strip fences, parse that shape,
    and return plain Gherkin text suitable for :func:`extract_quoted_spans_from_when_and_lines`.
    Otherwise return stripped text unchanged (already plain Gherkin).
    """
    stripped_fence = strip_markdown_code_fence(raw)
    flat = _flatten_user_intents_gherkin_json(stripped_fence)
    if flat is not None:
        return flat
    return stripped_fence


def one_to_one_match_count(
    ground_truth: list[str],
    candidates: list[str],
    *,
    threshold: float = 0.86,
) -> tuple[int, list[str]]:
    """
    Greedily assign each GT label to at most one candidate and vice versa.

    Returns (matched_count, unmatched_gt_labels).
    """
    if not ground_truth:
        return 0, []
    if not candidates:
        return 0, list(ground_truth)

    pairs: list[tuple[float, int, int]] = []
    for i, g in enumerate(ground_truth):
        for j, c in enumerate(candidates):
            score = string_similarity(g, c)
            if score >= threshold:
                pairs.append((score, i, j))
    pairs.sort(key=lambda t: t[0], reverse=True)

    used_gt: set[int] = set()
    used_c: set[int] = set()
    for _score, gi, cj in pairs:
        if gi in used_gt or cj in used_c:
            continue
        used_gt.add(gi)
        used_c.add(cj)

    unmatched = [ground_truth[i] for i in range(len(ground_truth)) if i not in used_gt]
    return len(used_gt), unmatched
