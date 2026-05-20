# UI State Extraction experiment

Offline experiment for joint screen understanding: generate raw vision outputs under `raw_outputs/`, then (module 2) build temp ground truth. This package imports `app` services but does not modify production code.

## Module 1: raw outputs

1. Set `IMAGE_ROOT_URL_OR_PATH` in [`config.py`](config.py) to a local directory or an `http(s)://` URL.
2. Ensure `.env` / `app.core.config` has working model credentials (same as the main app).
3. From the `be/` directory:

```bash
python -m experiments.ui_state_extraction.module_1_generate_raw_outputs
```

`pythonpath` is already `be/` for pytest; running the module requires the current working directory or `PYTHONPATH` to include `be/` so `experiments` and `app` resolve.

### Outputs

- Raw JSON per image: `raw_outputs/<mirrored path>/<stem>.raw.json` (`experiment_raw_output_v2`). Each file’s `model_call` includes `provider`, `model_name`, `latency_ms` (when the adapter returned a response), and `retry_count`.
- Manifest (schema `raw_output_manifest_v2`): `reports/raw_output_manifest.json` — paths are relative to this package root. The manifest adds `run_id`, **`experiment_model_settings`** (snapshot of `JOINT_SCREEN_UNDERSTANDING_*` + prompt + concurrency), **`model_latency_summary`** (mean/min/max `latency_ms` per actual provider/model), **`timing_notes`**, and per-item **`latency_ms` / `provider` / `model_name`** when a model call completed.
- Human-readable report: `reports/raw_output_report.md` — same model and latency summary as the manifest.

### HTTP image roots

Directory listing over HTTP is **best-effort**: HTML with `<a href="...">` links is crawled. Many CDNs and object stores do not expose directory listings; in that case use a local folder, a server that returns index pages, or point to a **direct image URL** for a single file.

### Flags (see `config.py`)

- `MAX_IMAGES_TO_PROCESS`: after discovery (list sorted by `relative_path`), process only the first N images; `0` = no limit (e.g. set to `5` for a quick test).
- `OVERWRITE_RAW_OUTPUT`: skip model calls when a `.raw.json` already exists (manifest marks `skipped`).

## Module 2: temp ground truth

[`module_2_build_temp_ground_truth.py`](module_2_build_temp_ground_truth.py) converts each raw JSON to a `.temp_gt.json` with the same schema as before. **Evaluation keys** `(element|action|feedback type, normalized label)` are **not** written into the GT file; they are derived at runtime via [`evaluation_key_service.py`](services/evaluation_key_service.py) (same as module 3).

**Action evaluation labels (GT, Sprint 5):** Keys use the first non-empty string from **`source_model_texts` → `text` → `anchor_texts`** so they stay aligned with raw model wording even when [`temp_ground_truth_builder_service`](services/temp_ground_truth_builder_service.py) rewrites `anchor_texts` during grounding.

**GT multiset view:** [`build_gt_evaluation_view`](services/ground_truth_normalizer_service.py) returns a [`GtEvaluationView`](services/ground_truth_normalizer_service.py) (mirrors [`PredEvaluationView`](services/pred_evaluation_view.py)) — `Counter`s of keys plus skip diagnostics — for multiset metrics vs predictions.

**Conversion `auto_flags` (Sprint 3+):** `element_key_missing:*`, `action_key_missing:*`, `feedback_key_missing:*`, `intent_key_missing:*` when a unit yields no evaluable key; label-first heuristics on input-like controls: `control_primary_text_looks_like_value:*`, `control_primary_text_masked_value:*`, `control_label_maybe_missing:*`. Legacy fields (`grounded_element_id`, `expected_steps`, etc.) are still populated for backward compatibility.

Verbose **module 2 debug JSONL** (`--debug-log-verbose`) adds an `evaluation_keys` object (string summaries per GT id) for converted images — useful for debugging without changing on-disk GT shape.

## Module 3: evaluation

This evaluation module is **experiment-only**. It does not modify the main pipeline. It ignores free-text / prose fields and focuses on:

- enum classification (screen taxonomy),
- text-grounded UI evidence (elements, feedback),
- action grounding,
- interaction group membership (Jaccard match),
- screen intent grounding (IDs and steps),
- invalid cross-reference counts,
- hallucinated (unmatched) predicted units.

**Element quality:** precision, recall, and F1 use only **text-grounded** predicted and GT elements (units with a non-empty evaluation key from [`services/evaluation_key_service.py`](services/evaluation_key_service.py): typed + `normalize_label` of primary anchor text). Greedy anchor **matching** still uses [`text_normalization_service.normalize_for_match`](services/text_normalization_service.py) via [`text_match_service`](services/text_match_service.py). Elements with no evaluable label are excluded from those denominators; their counts and rates are reported separately in evaluation outputs.

**Multiset key metrics (Sprint 6):** [`key_metric_service.py`](services/key_metric_service.py) implements `counter_prf` (`Σ_k min(pred[k], gt[k])` correctness) for element/action/feedback/intent `Counter`s. [`evaluate_pair`](services/metric_calculation_service.py) can run this path via [`MODULE3_USE_PRED_EVAL_VIEW_FOR_MAIN_METRICS`](config.py) or **`--key-metrics`** on [module 3](module_3_evaluate_ui_state_extraction.py). Screen taxonomy for scoring uses **three** enums (`presentation_scope`, `screen_type`, `outcome_state_type`; **not** `domain`) on both the multiset path and the default greedy path (`total_fields=3`).

**Dataset summary (Sprint 8):** [`evaluation_summary.json`](evaluation_reports/) uses schema version [`ui_state_extraction_evaluation_summary_v4`](config.py). [`aggregate_dataset_metrics_v4`](services/metric_calculation_service.py) fills **`aggregate_metrics`** (micro: pooled counter PRF + mean-per-image screen accuracies) and **`aggregate_metrics_macro`** (mean per-image P/R/F1; unit counts omitted). Legacy pooled metrics (`group_f1`, `action_grounding_accuracy`, intent multiset fields, `invalid_reference_rate`, `hallucination_rate`, empty-anchor tallies, attribute accuracies, etc.) are recorded under **`diagnostic_metrics`** only, not in the main aggregate blocks.

**Prediction vs GT multiset views:** [`build_prediction_evaluation_view`](services/prediction_normalizer_service.py) and [`build_gt_evaluation_view`](services/ground_truth_normalizer_service.py) (`Counter`s, shared [`evaluation_key_service`](services/evaluation_key_service.py)). [`normalize_raw_model_output`](services/prediction_normalizer_service.py) still builds [`PredictionEvaluationBundle`](schemas/evaluation_unit_schema.py) for greedy matching (default evaluator) and for debug logs.

**Synthetic unit tests:** many module 3 tests hand-craft bundles with intentionally incomplete raw JSON; leave `MODULE3_USE_PRED_EVAL_VIEW_FOR_MAIN_METRICS=False` unless raw matches Joint output (see [`../../tests/unit/test_key_metric_service.py`](../../tests/unit/test_key_metric_service.py)).

### Pipeline debug log (module 2 / 3)

Optional structured **JSONL** (one JSON object per line) for grep/`jq`, separate from `evaluation_per_image` debug tables:

- **Config:** [`config.EXPERIMENT_DEBUG_LOG_ENABLED`](config.py), [`EXPERIMENT_DEBUG_LOG_DIR`](config.py) (default `reports/pipeline_debug/`), [`EXPERIMENT_DEBUG_LOG_VERBOSE`](config.py).
- **CLI:** `--write-debug-log` and `--debug-log-verbose` on [module 2](module_2_build_temp_ground_truth.py) and [module 3](module_3_evaluate_ui_state_extraction.py) (flags override or extend config).
- Each run creates a timestamped file like `reports/pipeline_debug/experiment_debug_<UTC>.jsonl`.
- **Schema [`experiment_pipeline_debug_v2`](services/experiment_debug_log_service.py)** (both module 2 and 3 filenames unchanged): Module 3 lines add **`eval_key_debug`** multiset key blocks (`pred_keys`/`gt_keys`/`matched_keys`/`extra_keys`/`missing_keys` per category, plus **`skipped_units`** from pred/GT zero-key traces) built from **`compute_multiset_principal_metrics`** — independent of greedy `match_all_units` / `--key-metrics`. **`eval_key_debug_summary`** repeats Pred-extra / GT-missing imbalances as readable lines (`Pred extra (element): ('input','…')`).
- Module 3 still includes `intent_required_input_explain` (greedy remap: required ids, mapped GT ids, `dropped_pred_ids`); that path is orthogonal to multiset key-debug.

From the `be/` directory:

```bash
python -m experiments.ui_state_extraction.module_3_evaluate_ui_state_extraction
```

Dry run (counts only):

```bash
python -m experiments.ui_state_extraction.module_3_evaluate_ui_state_extraction --dry-run
```

Outputs are written under `evaluation_reports/` (see `config.EVALUATION_REPORT_DIR`): `evaluation_summary.json`, `evaluation_per_image.json`, `evaluation_summary.csv`, `evaluation_per_image.csv`, and `evaluation_report.md`.

**Reports (Sprint 10):** [`evaluation_per_image.csv`](services/evaluation_report_service.py) uses **33 columns**: three per-field screen accuracies plus combined screen enum accuracy; precision/recall/F1 and matched/pred/GT counts for elements, actions, feedback, and intents; and multiset **empty-key / intent-key-missing** diagnostics (`key_diagnostics` on each [`PerImageEvaluationResult`](schemas/evaluation_result_schema.py)). [`evaluation_report.md`](services/evaluation_report_service.py) is structured in **eight sections** (dataset summary → screen → four extraction families → key-skip diagnostics → notes). Legacy per-category CSVs (`element_metrics.csv`, …) are **not** written; deeper auxiliary metrics remain in [`evaluation_per_image.json`](evaluation_reports/) and **`diagnostic_metrics`** in `evaluation_summary.json`.

Optional flags: `--raw-output-dir`, `--ground-truth-dir`, `--output-dir`, `--group-threshold`, `--include-debug`, `--key-metrics`.

