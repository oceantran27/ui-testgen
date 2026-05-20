"""End-to-end evaluation: raw model output vs reviewed ground truth."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from experiments.flow_discovery.evaluator.branch_matcher import evaluate_branches
from experiments.flow_discovery.evaluator.error_analyzer import (
    analyze_errors,
    invalid_flow_fraction,
    invalid_pred_references,
)
from experiments.flow_discovery.evaluator.flow_matcher import evaluate_flows
from experiments.flow_discovery.evaluator.metric_calculator import (
    all_transition_items_for_report,
    build_metrics,
    transition_prf_from_bundle,
)
from experiments.flow_discovery.evaluator.prediction_normalizer import normalized_prediction_from_model
from experiments.flow_discovery.evaluator.report_writer import (
    write_evaluation_report,
    write_evaluation_summary_csv,
)
from experiments.flow_discovery.evaluator.transition_matcher import match_transitions
from experiments.flow_discovery.io_utils import read_json_document, write_json_document
from experiments.flow_discovery.schemas.evaluation_schema import EvaluationResult, FlowEvalItem
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage


def _pred_order_for_slice(pred_flows: List[Any], source_flow_id: str) -> List[str]:
    for pf in pred_flows:
        if isinstance(pf, dict) and str(pf.get("source_flow_id") or "").strip() == str(source_flow_id).strip():
            return list(pf.get("ordered_state_ids") or [])
    return []


def _flow_order_slices(gt: GroundTruthFlowPackage, pred_flows: List[Any], flow_items: List[FlowEvalItem]) -> List[Dict[str, Any]]:
    gt_flow_by_id = {f.gt_flow_id: f for f in gt.flows if getattr(f, "eval_include", True)}
    slices: list[dict[str, Any]] = []
    for fi in flow_items:
        fl = gt_flow_by_id.get(fi.gt_flow_id or "")
        if fl is None:
            continue
        sid = str(fl.source_flow_id or "").strip()
        slices.append(
            {
                "gt_flow_id": fl.gt_flow_id,
                "source_flow_id": sid,
                "ordering_accuracy": fi.ordering_accuracy,
                "ordering_errors": fi.ordering_errors,
                "gt_ordered_state_ids": list(fl.ordered_state_ids or []),
                "pred_ordered_state_ids": _pred_order_for_slice(pred_flows, sid),
                "membership_f1": fi.membership_f1,
            },
        )
    return slices


def _load_model_and_catalog(
    raw_path: Path,
) -> tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[str]]:
    data = read_json_document(raw_path)
    try:
        env = RawFlowDiscoveryExperimentPackage.model_validate(data)
    except Exception:
        if not isinstance(data, dict):
            raise ValueError("raw_output_must_be_object_or_envelope")
        return data, data.get("compressed_catalog_package"), None

    model = env.repaired_model_output or env.raw_model_output
    if not isinstance(model, dict):
        raise ValueError("envelope_missing_model_dict")
    return model, env.compressed_catalog_package, env.run_id


def run_evaluation(
    *,
    app_id: str,
    raw_output_path: Path,
    ground_truth_path: Path,
    out_dir: Path,
    run_id: Optional[str] = None,
) -> EvaluationResult:
    """Run full pipeline and write JSON, Markdown, and per-run CSV under ``out_dir``."""

    gt = GroundTruthFlowPackage.model_validate(read_json_document(ground_truth_path))
    model, compressed, env_run = _load_model_and_catalog(raw_output_path.resolve())

    norm = normalized_prediction_from_model(
        model,
        gt,
        compressed_catalog_package=compressed,
    )
    pred_rows = norm["predicted_transitions"]
    pred_flows = norm["predicted_flows"]
    pred_branches = norm["predicted_branch_groups"]

    gt_states = {s.gt_state_id for s in gt.states}
    gt_tx_eval = [t for t in gt.transitions if getattr(t, "eval_include", True)]

    bundle = match_transitions(pred_rows, gt_tx_eval)

    stp, sfp, sfn, _, _, _ = transition_prf_from_bundle(bundle, relaxed=False)
    rtp, rfp, rfn, _, _, _ = transition_prf_from_bundle(bundle, relaxed=True)
    transition_counts: Dict[str, Any] = {
        "strict": {"tp": int(stp), "fp": int(sfp), "fn": int(sfn)},
        "relaxed": {"tp": int(rtp), "fp": int(rfp), "fn": int(rfn)},
    }

    flow_items = evaluate_flows(gt, pred_rows, pred_flows)
    branch_items, bp, br, bf1 = evaluate_branches(gt, pred_rows, pred_branches)

    inv_n, inv_tags = invalid_pred_references(pred_rows, gt_states)
    inv_flow_rate = invalid_flow_fraction(pred_flows, gt_states)

    metrics = build_metrics(
        bundle,
        flow_items,
        bp,
        br,
        bf1,
        invalid_transition_count=inv_n,
        invalid_flow_rate=inv_flow_rate,
    )

    err = analyze_errors(
        bundle,
        flow_items,
        branch_items,
        invalid_transition_tags=inv_tags,
    )

    result = EvaluationResult(
        app_id=app_id.strip(),
        run_id=run_id or env_run,
        metrics=metrics,
        transition_items=all_transition_items_for_report(bundle),
        flow_items=flow_items,
        branch_items=branch_items,
        error_breakdown=err,
        extras={
            "normalized_prediction": norm,
            "transition_counts": transition_counts,
            "flow_order_slices": _flow_order_slices(gt, pred_flows, flow_items),
        },
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json_document(out_dir / "evaluation_result.json", result.model_dump(mode="json", round_trip=True))
    write_evaluation_report(out_dir / "evaluation_report.md", result)
    write_evaluation_summary_csv(out_dir / "evaluation_summary.csv", result)

    return result
