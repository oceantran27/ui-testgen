"""Unit tests for key_metric_service (Sprint 6 multiset Counter PRF)."""

from __future__ import annotations

from collections import Counter

import pytest

from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ImageMetaInRawOutput,
    ModelCallMeta,
)
from experiments.ui_state_extraction.services.key_metric_service import counter_prf, compute_multiset_principal_metrics
from experiments.ui_state_extraction.services.metric_calculation_service import evaluate_pair
from experiments.ui_state_extraction.services.prediction_normalizer_service import normalize_raw_model_output
from experiments.ui_state_extraction.services.temp_ground_truth_builder_service import (
    build_temp_ground_truth_from_raw,
)

from tests.unit.test_ui_state_extraction_module2 import _login_raw_payload


def test_counter_prf_duplicate_keys_acceptance_example() -> None:
    pred = Counter({("button", "edit"): 1})
    gt = Counter({("button", "edit"): 2})
    r = counter_prf(pred, gt)
    assert r.correct_count == 1
    assert r.pred_count == 1
    assert r.gt_count == 2
    assert r.precision == 1.0
    assert r.recall == 0.5
    assert r.f1 is not None and pytest.approx(r.f1, abs=1e-4) == pytest.approx(2 / 3, abs=1e-4)
    assert dict(r.extra) == {}
    assert dict(r.missing) == {("button", "edit"): 1}


def test_counter_prf_both_empty() -> None:
    r = counter_prf(Counter(), Counter())
    assert r.correct_count == 0
    assert r.precision is None
    assert r.recall is None
    assert r.f1 is None


def test_evaluate_login_key_counters_matches_manual_multiset() -> None:
    raw = _login_raw_payload()
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="exp_auth_login_login_empty",
            relative_path="auth/login/login_empty.png",
            filename="login_empty.png",
            stem="login_empty",
            extension=".png",
            source_path="/dataset/auth/login/login_empty.png",
        ),
        model_call=ModelCallMeta(status="success", created_at=""),
        raw_model_output=raw,
    )
    gt = build_temp_ground_truth_from_raw(
        doc,
        source_raw_output_path="raw_outputs/auth/login/login_empty.raw.json",
        validate_joint_schema=True,
    )
    bundle, _pv, _gv = compute_multiset_principal_metrics(raw, gt)
    pred = normalize_raw_model_output(raw)

    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=True, use_key_counters=True)

    assert res.screen_metrics.total_fields == 3
    assert res.screen_metrics.correct_fields == 3
    assert res.screen_metrics.accuracy == pytest.approx(1.0)
    assert res.element_metrics.text_grounded_matched_count == bundle.element.correct_count
    assert res.element_metrics.f1 == pytest.approx(bundle.element.f1 or 1.0)
    assert res.action_metrics.f1 == pytest.approx(bundle.action.f1 or 1.0)
    assert res.intent_metrics.f1 == pytest.approx(bundle.intent.f1 or 1.0)
    assert "keyMultiset" in res.debug
