"""Match pipeline flow cards / edges to DemoBooking BOOK_Sxx anchors and compute recall vs ground_truth_flows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

_FIXTURE_DIR = Path(__file__).resolve().parent


def load_fixture_screens(fixture_dir: Path | None = None) -> List[Dict[str, Any]]:
    d = fixture_dir or _FIXTURE_DIR
    with open(d / "screens.json", encoding="utf-8") as f:
        return json.load(f)


def load_ground_truth_flows(fixture_dir: Path | None = None) -> List[Dict[str, Any]]:
    d = fixture_dir or _FIXTURE_DIR
    with open(d / "ground_truth_flows.json", encoding="utf-8") as f:
        return json.load(f)


def match_state_cards_to_book_screens(
    flow_state_cards: Sequence[MutableMapping[str, Any]],
    screens_meta: Sequence[Mapping[str, Any]],
    *,
    min_hint_hits_non_modal: int = 2,
    min_hint_hits_modal: int = 1,
) -> Dict[str, str]:
    """
    Map canonical state_id -> book_screen_id (BOOK_Sxx).
    Prefer higher hint overlap; BOOK_S03 vs BOOK_S08 disambiguated by unique alert copy on S08.
    """
    state_to_book: Dict[str, str] = {}
    scored: Dict[str, Tuple[int, str]] = {}

    for card in flow_state_cards:
        sid = str(card.get("state_id") or "")
        if not sid:
            continue
        corp_bits = []
        corp_bits.extend(card.get("visible_text") or [])
        corp_bits.extend(card.get("feedback_texts") or [])
        corp = " ".join(str(x) for x in corp_bits).lower()
        out = str(card.get("outcome_state_type") or "").lower()
        ps = str(card.get("presentation_scope") or "").lower()

        best_bid = ""
        best_adj = -1
        best_hits = 0

        for spec in screens_meta:
            bid = str(spec["book_screen_id"])
            hints = [str(h).lower() for h in spec.get("canonical_title_hints") or []]
            hits = sum(1 for h in hints if h and h in corp)
            # Disambiguate S03 vs S08: S08 requires error outcome + slot message
            if bid == "BOOK_S08" and out not in ("error", "warning"):
                continue
            if bid == "BOOK_S08" and "no longer available" not in corp and "slot" not in corp:
                # still allow if strong unique hint
                if hits < 2:
                    continue
            if bid == "BOOK_S03" and out in ("error", "validation_error") and "no longer" in corp:
                continue

            min_h = min_hint_hits_modal if spec.get("presentation_scope") == "modal" else min_hint_hits_non_modal
            if hits < min_h and bid not in ("BOOK_S10",):
                # modal often has short visible chrome in crop
                if not (spec.get("presentation_scope") == "modal" and hits >= min_hint_hits_modal):
                    continue

            expect_out = str(spec.get("expected_outcome") or "").lower()
            if expect_out and out and out != "unknown" and expect_out != out:
                # soft penalty: still count but deprioritize
                adj = hits - 1
            else:
                adj = hits

            if adj > best_adj or (adj == best_adj and hits > best_hits):
                best_adj = adj
                best_hits = hits
                best_bid = bid

        if best_bid:
            scored[sid] = (best_adj, best_bid)

    # resolve collisions: one state per book id / unique assignment
    by_book: Dict[str, List[str]] = {}
    for sid, (_sc, bid) in scored.items():
        by_book.setdefault(bid, []).append(sid)

    for bid, sids in by_book.items():
        if len(sids) <= 1:
            for s in sids:
                state_to_book[s] = bid
            continue
        best_sid = max(sids, key=lambda x: scored.get(x, (0, bid))[0])
        state_to_book[best_sid] = bid

    return state_to_book


def _edge_pair_set(
    edges: Sequence[Mapping[str, Any]],
    state_to_book: Mapping[str, str],
) -> set[Tuple[str, str]]:
    pairs: set[Tuple[str, str]] = set()
    for e in edges:
        fs = str(e.get("from_state") or "")
        ts = str(e.get("to_state") or "")
        fb = state_to_book.get(fs)
        tb = state_to_book.get(ts)
        if fb and tb:
            pairs.add((fb, tb))
    return pairs


def evaluate_verified_transitions(
    verified_edges: Sequence[Mapping[str, Any]],
    flow_state_cards: Sequence[MutableMapping[str, Any]],
    screens_meta: Sequence[Mapping[str, Any]] | None = None,
    gt_flows: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Return metrics: per-flow edge coverage, total GT edges matched."""
    screens_meta = screens_meta or load_fixture_screens()
    gt_flows = gt_flows or load_ground_truth_flows()
    stb = match_state_cards_to_book_screens(flow_state_cards, screens_meta)
    v_pairs = _edge_pair_set(verified_edges, stb)

    flow_results = []
    total_gt = 0
    total_hit = 0

    for fl in gt_flows:
        screens = list(fl["screens"])
        missing = []
        for i in range(len(screens) - 1):
            total_gt += 1
            need = (screens[i], screens[i + 1])
            ok = need in v_pairs
            total_hit += 1 if ok else 0
            if not ok:
                missing.append(need)

        flow_results.append(
            {
                "flow_id": fl["flow_id"],
                "intent_slug": fl.get("intent_slug"),
                "gt_edge_count": len(screens) - 1,
                "matched_edges": (len(screens) - 1) - len(missing),
                "missing_book_pairs": missing,
            }
        )

    return {
        "state_to_book_matches": len(stb),
        "distinct_book_ids": sorted(set(stb.values())),
        "transition_recall_hit": total_hit,
        "transition_recall_total": total_gt,
        "flow_results": flow_results,
    }


def evaluate_discovery_flows(
    discovery: Mapping[str, Any],
    flow_state_cards: Sequence[MutableMapping[str, Any]],
    screens_meta: Sequence[Mapping[str, Any]] | None = None,
    gt_flows: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Check each GT sequence is a subpath of some candidate_flow ordered_states (after book mapping)."""
    screens_meta = screens_meta or load_fixture_screens()
    gt_flows = gt_flows or load_ground_truth_flows()
    stb = match_state_cards_to_book_screens(flow_state_cards, screens_meta)
    books = gt_flows  # shorthand

    def states_to_book_path(ordered_states: Sequence[str]) -> List[str]:
        return [stb[s] for s in ordered_states if stb.get(s)]

    flows_out = []
    cfs = discovery.get("candidate_flows") or []

    for fl in books:
        need = fl["screens"]
        best_cov = 0
        best_fid = None
        for cf in cfs:
            os_raw = cf.get("ordered_states") or []
            path = states_to_book_path(os_raw)
            cov = _longest_common_subsequence_len(need, path)
            if cov > best_cov:
                best_cov = cov
                best_fid = cf.get("flow_id")
        flows_out.append(
            {
                "flow_id": fl["flow_id"],
                "need_len": len(need),
                "best_subsequence_hit": best_cov,
                "best_candidate_flow_id": best_fid,
                "detected_full_sequence": bool(best_cov >= len(need)),
            }
        )

    return {"flow_subsequence_checks": flows_out, "candidate_flow_count": len(cfs)}


def _longest_common_subsequence_len(a: Sequence[str], b: Sequence[str]) -> int:
    """LCS length (canonical labels)."""
    if not a or not b:
        return 0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if a[i - 1] == b[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
    return dp[-1][-1]


def evaluate_final_output_keywords(
    final_output: Mapping[str, Any],
) -> Dict[str, Any]:
    """Cheap scenario smoke: substring hits for DemoBooking intents."""
    scenarios = final_output.get("behaviour_scenarios") or []
    keywords = [
        ("BOOK_F01", ["book", "confirm", "appointment", "Dental"]),
        ("BOOK_F02", ["validation", "required", "contact"]),
        ("BOOK_F03", ["slot", "available", "time"]),
        ("BOOK_F04", ["edit", "time"]),
        ("BOOK_F05", ["cancel", "appointment"]),
    ]
    hits = []
    blob = json.dumps(scenarios, default=str).lower()
    for fid, kws in keywords:
        hits.append({"flow_id": fid, "hit": any(k.lower() in blob for k in kws)})
    return {"keyword_hits": hits, "exported_scenario_count": len(scenarios)}


def compressed_card_corpora(card: Mapping[str, Any]) -> str:
    """Lowercased text blob for aligning compressed cards to BOOK_Sxx hint lists."""
    tax = card.get("taxonomy") if isinstance(card.get("taxonomy"), dict) else {}
    bits: List[str] = [
        str(card.get("screen_purpose") or ""),
        str(tax.get("domain") or card.get("domain") or ""),
        str(tax.get("presentation_scope") or card.get("presentation_scope") or ""),
        str(tax.get("outcome_state_type") or card.get("outcome_state_type") or ""),
    ]
    for row in card.get("state_feedback_summary") or []:
        if isinstance(row, dict):
            for t in row.get("text") or []:
                bits.append(str(t))
    for g in card.get("intent_groups") or []:
        if not isinstance(g, dict):
            continue
        bits.append(str(g.get("local_user_goal") or g.get("user_intent") or ""))
        bits.append(str(g.get("intent_name") or ""))
        for pa_key in ("primary_action", "commit_action"):
            pa = g.get(pa_key)
            if isinstance(pa, dict):
                bits.extend(str(t) for t in (pa.get("text") or []))
        for sa in g.get("secondary_actions") or []:
            if isinstance(sa, dict):
                bits.extend(str(t) for t in (sa.get("text") or []))
        for x in g.get("primary_actions") or []:
            bits.append(str(x))
        for x in g.get("feedback_signals") or []:
            bits.append(str(x))
    return " ".join(x for x in bits if x).lower()


def compressed_catalog_as_flow_state_cards(
    compressed_catalog: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Adaptor: BOOK_Sxx matching via match_state_cards_to_book_screens on compressed artefacts."""

    out: List[Dict[str, Any]] = []
    for c in compressed_catalog:
        corp = compressed_card_corpora(c)
        tax = c.get("taxonomy") if isinstance(c.get("taxonomy"), dict) else {}
        out.append(
            {
                "state_id": str(c.get("state_id") or ""),
                "visible_text": [corp] if corp else [],
                "feedback_texts": [],
                "outcome_state_type": str(tax.get("outcome_state_type") or c.get("outcome_state_type") or ""),
                "presentation_scope": str(
                    tax.get("presentation_scope") or c.get("presentation_scope") or ""
                ).lower(),
            }
        )
    return out


def evaluate_global_discovery_on_compressed_catalog(
    flow_discovery_bundle: Mapping[str, Any],
    compressed_catalog: Sequence[Mapping[str, Any]],
    screens_meta: Sequence[Mapping[str, Any]] | None = None,
    gt_flows: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Thesis grading: GT subsequence recall when discovery comes from compressed global batch path."""

    pseudo = compressed_catalog_as_flow_state_cards(compressed_catalog)
    return evaluate_discovery_flows(
        dict(flow_discovery_bundle),
        pseudo,
        screens_meta=screens_meta,
        gt_flows=gt_flows,
    )
