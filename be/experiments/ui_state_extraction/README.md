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

- Raw JSON per image: `raw_outputs/<mirrored path>/<stem>.raw.json`
- Manifest: `reports/raw_output_manifest.json` (paths in the manifest are relative to this package root).

### HTTP image roots

Directory listing over HTTP is **best-effort**: HTML with `<a href="...">` links is crawled. Many CDNs and object stores do not expose directory listings; in that case use a local folder, a server that returns index pages, or point to a **direct image URL** for a single file.

### Flags (see `config.py`)

- `MAX_IMAGES_TO_PROCESS`: after discovery (list sorted by `relative_path`), process only the first N images; `0` = no limit (e.g. set to `5` for a quick test).
- `OVERWRITE_RAW_OUTPUT`: skip model calls when a `.raw.json` already exists (manifest marks `skipped`).

## Module 3: evaluation

This evaluation module is **experiment-only**. It does not modify the main pipeline. It ignores free-text / prose fields and focuses on:

- enum classification (screen taxonomy),
- text-grounded UI evidence (elements, feedback),
- action grounding,
- interaction group membership (Jaccard match),
- screen intent grounding (IDs and steps),
- invalid cross-reference counts,
- hallucinated (unmatched) predicted units.

**Element quality:** precision, recall, and F1 use only **text-grounded** predicted and GT elements (anchors non-empty after the same normalization as matching). Elements with empty anchors (e.g. decorative regions) are excluded from those denominators; their counts and rates are reported separately in evaluation outputs.

### Pipeline debug log (module 2 / 3)

Optional structured **JSONL** (one JSON object per line) for grep/`jq`, separate from `evaluation_per_image` debug tables:

- **Config:** [`config.EXPERIMENT_DEBUG_LOG_ENABLED`](config.py), [`EXPERIMENT_DEBUG_LOG_DIR`](config.py) (default `reports/pipeline_debug/`), [`EXPERIMENT_DEBUG_LOG_VERBOSE`](config.py).
- **CLI:** `--write-debug-log` and `--debug-log-verbose` on [module 2](module_2_build_temp_ground_truth.py) and [module 3](module_3_evaluate_ui_state_extraction.py) (flags override or extend config).
- Each run creates a timestamped file like `reports/pipeline_debug/experiment_debug_<UTC>.jsonl`.
- Module 3 lines include `intent_required_input_explain` (raw required ids, mapped GT ids after element match, `dropped_pred_ids` when pred id ∉ `el_m`).

From the `be/` directory:

```bash
python -m experiments.ui_state_extraction.module_3_evaluate_ui_state_extraction
```

Dry run (counts only):

```bash
python -m experiments.ui_state_extraction.module_3_evaluate_ui_state_extraction --dry-run
```

Outputs are written under `evaluation_reports/` (see `config.EVALUATION_REPORT_DIR`): `evaluation_summary.json`, `evaluation_per_image.json`, CSVs, and `evaluation_report.md`.

Optional flags: `--raw-output-dir`, `--ground-truth-dir`, `--output-dir`, `--group-threshold`, `--include-debug`.

