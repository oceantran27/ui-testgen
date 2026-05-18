"""Deterministic Gherkin keyword / anchor grounding checks (Agent 6 pre-audit)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple

from app.services.ui_text_normalize import normalize_ui_text

_PLACEHOLDER_RE = re.compile(r"<([^>]+)>")

# Backend id literals that sometimes leak into step text — only common pipeline prefixes.
_LEAK_ID_RE = re.compile(
    r"\b(?:bi_|tr_|fb_|intent_|flow_|grp_|sf_|fi_)[a-zA-Z0-9]+(?:_[a-zA-Z0-9]+)*\b",
    re.I,
)


def _split_bdd_sections(steps: List[Dict[str, Any]]) -> Tuple[str, str, str]:
    phase = "given"
    chunks_g: List[str] = []
    chunks_w: List[str] = []
    chunks_t: List[str] = []
    for raw in steps or []:
        kw = str(raw.get("keyword") or "").strip().lower()
        if kw == "when":
            phase = "when"
        elif kw == "then":
            phase = "then"
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        if phase == "given":
            chunks_g.append(text)
        elif phase == "when":
            chunks_w.append(text)
        else:
            chunks_t.append(text)
    return " ".join(chunks_g), " ".join(chunks_w), " ".join(chunks_t)


def _text_matches_anchor(section_norm: str, anchor_text: str, match_type: str) -> bool:
    an = normalize_ui_text(anchor_text)
    if not an:
        return True
    sn = normalize_ui_text(section_norm)
    if not sn:
        return False
    if match_type == "exact":
        return an == sn or an == normalize_ui_text(sn)
    # exact_or_contained
    return an in sn or sn in an


def _anchors_for_section(ma: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "given": ma.get("given") or [],
        "when": ma.get("when") or [],
        "then": ma.get("then") or [],
    }


def validate_scenario_against_blueprint(scenario: Dict[str, Any], blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates step text against blueprint mandatory anchors; ignores LLM self-reported anchor_ids_used.
    """
    steps_raw = scenario.get("steps") or []
    mandatory = _anchors_for_section(blueprint.get("mandatory_anchors") or {})
    given_t, when_t, then_t = _split_bdd_sections(steps_raw if isinstance(steps_raw, list) else [])

    required_ids: List[str] = []
    matched_ids: List[str] = []
    missing: List[str] = []
    wrong_section: List[str] = []
    matched = 0

    def section_for(name: str) -> str:
        if name == "given":
            return given_t
        if name == "when":
            return when_t
        return then_t

    section_anchor_total = {"given": 0, "when": 0, "then": 0}
    section_anchor_hit = {"given": 0, "when": 0, "then": 0}

    for sec_name in ("given", "when", "then"):
        for a in mandatory[sec_name]:
            aid = str(a.get("anchor_id") or "").strip()
            txt = str(a.get("text") or "").strip()
            mtype = str(a.get("match_type") or "exact_or_contained").strip()
            if not aid:
                continue
            required_ids.append(aid)
            section_anchor_total[sec_name] += 1
            if _text_matches_anchor(section_for(sec_name), txt, mtype):
                matched += 1
                matched_ids.append(aid)
                section_anchor_hit[sec_name] += 1
            else:
                # wrongly placed vs missing: try other sections once
                placed_elsewhere = False
                for other in ("given", "when", "then"):
                    if other == sec_name:
                        continue
                    if _text_matches_anchor(section_for(other), txt, mtype):
                        wrong_section.append(aid)
                        placed_elsewhere = True
                        break
                if not placed_elsewhere:
                    missing.append(aid)

    allow_ph = set(blueprint.get("allowed_test_data_placeholders") or [])
    unexpected_ph: List[str] = []

    corpus = "\n".join(str(s.get("text") or "") for s in steps_raw if isinstance(s, dict))
    for m in _PLACEHOLDER_RE.finditer(corpus):
        wrapped = m.group(0)
        inner_norm = normalize_ui_text(m.group(1).strip()).replace(" ", "_")
        equiv = f"<{inner_norm}>"
        if wrapped not in allow_ph and equiv not in allow_ph:
            unexpected_ph.append(wrapped)

    trace = blueprint.get("traceability") or {}
    allow_ids: Set[str] = set()
    for key in ("source_intent_id", "source_flow_id"):
        bv = blueprint.get(key)
        if bv:
            allow_ids.add(str(bv))
    for sid in [(scenario.get("start_state")), scenario.get("end_state")]:
        if sid:
            allow_ids.add(str(sid))
    for x in trace.get("source_transition_ids") or []:
        if x:
            allow_ids.add(str(x))
    tid = trace.get("trigger_action_id")
    if tid:
        allow_ids.add(str(tid))
    for fid in trace.get("expected_feedback_ids") or []:
        if fid:
            allow_ids.add(str(fid))
    ssi = trace.get("source_screen_intent_id")
    if ssi:
        allow_ids.add(str(ssi))

    allow_lower = {str(x).lower() for x in allow_ids if x}
    invalid_trace_refs: List[str] = []
    for m in _LEAK_ID_RE.finditer(corpus):
        token = m.group(0)
        if token.lower() not in allow_lower:
            invalid_trace_refs.append(token)

    required_count = len(required_ids)
    coverage = matched / required_count if required_count else 1.0

    def cov_ratio(hit: int, total: int) -> float:
        return hit / total if total else 1.0

    grounding_passed = (
        not missing
        and not wrong_section
        and not unexpected_ph
        and matched == required_count
        and not invalid_trace_refs
    )

    return {
        "required_anchor_count": required_count,
        "matched_anchor_count": matched,
        "missing_anchor_ids": missing,
        "wrong_section_anchor_ids": wrong_section,
        "unexpected_placeholders": unexpected_ph,
        "invalid_trace_refs": invalid_trace_refs,
        "matched_anchor_ids": matched_ids,
        "grounding_passed": grounding_passed,
        "keyword_anchor_coverage": coverage,
        "section_coverage_given": cov_ratio(section_anchor_hit["given"], section_anchor_total["given"]),
        "section_coverage_when": cov_ratio(section_anchor_hit["when"], section_anchor_total["when"]),
        "section_coverage_then": cov_ratio(section_anchor_hit["then"], section_anchor_total["then"]),
    }