# Flow discovery experiment

## Mục tiêu

Đo và báo cáo chất lượng **global flow discovery** của model so với **ground truth được review tay**: nhận biết sai lệch ở mức transition (strict/relaxed), flow membership + thứ tự màn hình, nhánh UX (branch outcomes), và tham chiếu không hợp lệ.

---

## Chạy nhanh (lệnh ngắn)

1. Mở [`config.py`](config.py) và chỉnh các biến `CLI_*` (đường dẫn **relative tới thư mục `flow_discovery/`**, trừ khi bạn dùng đường dẫn tuyệt đối).
2. Từ thư mục `be/`:

```bash
cd be
set PYTHONPATH=.
python -m experiments.flow_discovery.cli print-config
python -m experiments.flow_discovery.cli build-compressed
python -m experiments.flow_discovery.cli run-one-from-joint-raw
python -m experiments.flow_discovery.cli raw-capture
python -m experiments.flow_discovery.cli gt-convert
python -m experiments.flow_discovery.cli gt-validate
python -m experiments.flow_discovery.cli evaluate
python -m experiments.flow_discovery.cli run-one
python -m experiments.flow_discovery.cli build-compressed-batch
python -m experiments.flow_discovery.cli run-batch
```

Trên Linux/macOS: `export PYTHONPATH=.`

`print-config` in JSON toàn bộ giá trị `CLI_*` sau khi resolve path (kiểm tra trước khi gọi LLM).

### Ghi đè bằng CLI

Mọi flag vẫn hoạt động: nếu truyền (ví dụ `--work-dir`, `--compressed-catalog`), giá trị đó **thay thế** mặc định trong `config.py`. Hữu ích cho pytest/CI hoặc chạy một lần không đổi file config.

---

## Cấu hình: biến trong [`config.py`](config.py)

| Biến | Ý nghĩa |
|------|---------|
| `CLI_APP_ID` | App / tenant thí nghiệm |
| `CLI_WORK_DIR` | Thư mục làm việc (`run-one`, `run-one-from-joint-raw`) |
| `CLI_RAW_JOINT_DIR` | Thư mục `*.raw.json` (joint screen understanding) |
| `CLI_INPUT_BUILDER_OUT_DIR` | Output `build-compressed` (chứa `compressed_catalog_package.json`) |
| `CLI_IMAGE_MAP_PATH` | Optional `image_map.json` cho input_builder |
| `CLI_INPUT_BUILDER_STRICT` | Strict mode input_builder |
| `CLI_COMPRESSED_CATALOG_PATH` | Catalog nén đầu vào `raw-capture` / `run-one` |
| `CLI_RAW_CAPTURE_OUTPUT_PATH` | File envelope sau `raw-capture` |
| `CLI_GROUND_TRUTH_REVIEWED_PATH` | Optional; `None` → `<work-dir>/ground_truth.reviewed.json` (`run-one`) |
| `CLI_GT_CONVERT_RAW_OUTPUT` / `CLI_GT_CONVERT_OUT` | Input/output `gt-convert` |
| `CLI_GT_VALIDATE_INPUT` / `CLI_GT_VALIDATE_OUT` | Input/output `gt-validate` (`OUT` có thể `None` = ghi đè file input) |
| `CLI_EVAL_*` | `evaluate`: raw, GT reviewed, thư mục output |
| `CLI_RUN_BATCH_MANIFEST` / `CLI_RUN_BATCH_OUT_DIR` | `run-batch` (manifest để trống = bắt buộc `--manifest`) |
| `CLI_RUN_BATCH_FAIL_FAST` | Dừng batch khi app đầu fail |
| `CLI_BUILD_COMPRESSED_BATCH_MANIFEST` / `CLI_BUILD_COMPRESSED_BATCH_STRICT` | Batch `build-compressed` |
| `CLI_RUN_ID`, `CLI_PROMPT_VERSION`, `CLI_PROMPT_NAME`, `CLI_PROVIDER`, `CLI_MODEL`, `CLI_MAX_CATALOG_SCREENS` | Tuỳ chọn model / prompt |
| `CLI_SKIP_RAW_CAPTURE` | `run-one`: bỏ qua bước capture (chỉ evaluate) |
| `CLI_VALIDATE_CATALOG_SCREEN_COUNT` | Bật guard kích thước catalog (tắt bằng `--skip-catalog-screen-check` trên CLI) |

Hàm [`resolve_cli_path`](config.py) resolve chuỗi relative theo `PACKAGE_ROOT` của package này.

---

## Inputs / outputs

| Artefact | Schema / vai trò |
|----------|------------------|
| `compressed_catalog_package.json` | Compressed catalogue đầu vào của experiment (offline). |
| `raw_model_output.json` | [`RawFlowDiscoveryExperimentPackage`](schemas/raw_output_schema.py) — chứa `raw_model_output` / `repaired_model_output`. |
| `ground_truth.draft.json` | [`GroundTruthFlowPackage`](schemas/ground_truth_schema.py) nháp sau `gt-convert`. |
| `ground_truth.reviewed.json` | Ground truth đã chỉnh + review; evaluator nhận bản đã review. |

### Luồng joint raw → compressed (`input_builder`)

Khi chỉ có output raw từ `prompt_joint_screen_understanding_v1` (`*.raw.json`), dùng `build-compressed` (sau khi cấu hình `CLI_RAW_JOINT_DIR` + `CLI_INPUT_BUILDER_OUT_DIR`) rồi `raw-capture` như bình thường. Mỗi file joint có thể đặt `ui_state` / `screen_intents` ở root, lồng trong `parsed_output` / `output`, hoặc trong `raw_model_output` (envelope `experiment_raw_output_v1`).

Luồng một lệnh tới GT draft (không evaluate): **`run-one-from-joint-raw`** — ghi:

- `<work_dir>/input_builder/` (catalog + sidecar),
- `<work_dir>/raw_model_output.json`,
- `<work_dir>/gt_converter/ground_truth.draft.json`.

### Layout thư mục

**`run-one` / dataset** (ví dụ [`fixtures/demoauth`](fixtures/demoauth)):

```text
<work-dir>/
  raw_model_output.json
  ground_truth.reviewed.json
  evaluation/
    evaluation_result.json
    evaluation_report.md
    evaluation_summary.csv
```

**`run-one-from-joint-raw`:**

```text
<work-dir>/
  input_builder/
    compressed_catalog_package.json
    ...
  raw_model_output.json
  gt_converter/
    ground_truth.draft.json
```

**Batch (`run-batch`)**: `--out-dir` chứa `evaluation_summary.csv`, `batch_manifest_used.json`, có thể `batch_failures.jsonl`.

Fixtures offline: [`fixtures/demoauth`](fixtures/demoauth). Tạo lại JSON:

```bash
cd be
PYTHONPATH=. python experiments/flow_discovery/fixtures/demoauth/_generate_fixtures.py
```

Module **chỉ thí nghiệm** dưới [`be/experiments/flow_discovery`](.). Không sửa production `be/app/`. Import `app.*` chỉ qua [`adapters/`](adapters/).

Chạy test: `PYTHONPATH=. pytest tests/experiments/flow_discovery/` từ thư mục `be/`.

---

## Tests

- Package: [`../../tests/experiments/flow_discovery/`](../../tests/experiments/flow_discovery/).
- Legacy: [`../../tests/unit/`](../../tests/unit/) — `test_flow_discovery_*.py`.

---

## Import policy

- **All** imports from production (`from app.` / `import app`) MUST live under [`adapters/`](adapters/).
- Optional future exception (document here if adopted): [`app.core.logging.logger`](../../app/core/logging) for structured logging outside adapters.

---

## Roadmap

| Sprint | Focus | Deliverable |
|--------|-------|--------------|
| 0 | Scaffold + read-only adapters | Tree, adapters, README |
| 1 | Experiment schemas | `schemas/*` |
| 2 | `raw_capture/` | Persist `raw_flow_discovery_experiment_package.json` |
| 3 | `gt_converter/` | `ground_truth.draft.json` |
| 4 | Draft auto-validation | Review hints |
| 5 | `evaluator/` | Metrics JSON + Markdown + `evaluate` CLI |
| 6 | CLI + orchestration | `run-one`, `run-batch`, CSV + report polish (**done**) |
| 7 | Fixtures + docs | `fixtures/demoauth`, structured tests (**done**) |

Modules:

1. **raw_capture** — model raw output envelope  
2. **gt_converter** — raw → reviewable ground truth  
3. **evaluator** — predictions vs reviewed GT ([`evaluator/`](evaluator/))  

[`pipeline_runner.py`](pipeline_runner.py) orchestrates raw capture → evaluation.

---

## Phụ lục: ví dụ lệnh đầy đủ (không dùng `config.py`)

Dưới đây là các lệnh tương đương khi truyền đủ đường dẫn explicit.

### Raw capture (`raw-capture`)

```bash
cd be
PYTHONPATH=. python -m experiments.flow_discovery.cli raw-capture ^
  --app-id demoauth ^
  --compressed-catalog experiments/flow_discovery/fixtures/demoauth/compressed_catalog_package.json ^
  --out experiments/flow_discovery/outputs/cli_work/demoauth/raw_model_output.json
```

(Linux: bỏ `^`, dùng `\` hoặc một dòng.)

Optional: `--run-id`, `--prompt-version`, `--prompt-name`, `--provider`, `--model`, `--max-catalog-screens`, `--skip-catalog-screen-check`.

### Ground truth draft (`gt-convert`)

```bash
PYTHONPATH=. python -m experiments.flow_discovery.cli gt-convert ^
  --app-id demoauth ^
  --raw-output experiments/flow_discovery/fixtures/demoauth/raw_model_output.json ^
  --out experiments/flow_discovery/outputs/cli_work/demoauth/ground_truth.draft.json
```

### Review ground truth (`gt-validate`)

```bash
PYTHONPATH=. python -m experiments.flow_discovery.cli gt-validate ^
  --input experiments/flow_discovery/fixtures/demoauth/ground_truth.reviewed.sample.json
```

Optional `--out` hoặc `--stdout`.

### Evaluate (`evaluate`)

```bash
PYTHONPATH=. python -m experiments.flow_discovery.cli evaluate ^
  --app-id demoauth ^
  --raw-output experiments/flow_discovery/fixtures/demoauth/raw_model_output.json ^
  --ground-truth experiments/flow_discovery/fixtures/demoauth/ground_truth.reviewed.sample.json ^
  --out-dir experiments/flow_discovery/outputs/cli_work/demoauth/evaluation
```

### `run-one`

```bash
PYTHONPATH=. python -m experiments.flow_discovery.cli run-one ^
  --app-id demoauth ^
  --compressed-catalog experiments/flow_discovery/fixtures/demoauth/compressed_catalog_package.json ^
  --work-dir path/to/work
```

- `--skip-raw-capture` — chỉ evaluate (cần `raw_model_output.json` trong work-dir).
- `--ground-truth` — override GT reviewed.

### Joint → compressed & pipeline

```bash
PYTHONPATH=. python -m experiments.flow_discovery.cli build-compressed ^
  --app-id demoauth ^
  --raw-joint-dir experiments/flow_discovery/fixtures/demoauth/raw_joint_outputs ^
  --out-dir experiments/flow_discovery/outputs/cli_work/demoauth/input_builder

PYTHONPATH=. python -m experiments.flow_discovery.cli run-one-from-joint-raw ^
  --app-id demoauth ^
  --raw-joint-dir experiments/flow_discovery/fixtures/demoauth/raw_joint_outputs ^
  --work-dir experiments/flow_discovery/outputs/cli_work/demoauth
```

### `build-compressed-batch`

```bash
PYTHONPATH=. python -m experiments.flow_discovery.cli build-compressed-batch ^
  --manifest experiments/flow_discovery/fixtures/apps_manifest_joint_raw.json
```

### `run-batch`

Manifest JSON: paths relative tới `PACKAGE_ROOT` của package này hoặc absolute. Ví dụ skeleton: [`fixtures/apps_manifest.json`](fixtures/apps_manifest.json) (tạo/tùy chỉnh theo dataset).

```bash
PYTHONPATH=. python -m experiments.flow_discovery.cli run-batch ^
  --manifest path/to/manifest.json ^
  --out-dir experiments/flow_discovery/outputs/batch_out
```

Trường `skip_raw_capture: true` để chỉ evaluate offline.

`--fail-fast` — dừng khi app đầu fail.

---

## Định nghĩa metric

| Khía cạnh | Ý nghĩa |
|-----------|---------|
| **Transition strict** | Khớp from/to/state, trigger normalized, và `outcome_type`. |
| **Transition relaxed** | Giống strict nhưng bỏ so khớp `outcome_type` — relaxed TP vẫn có thể gắn tag `wrong_outcome_type`. |
| **Flow membership_macro_f1** | Macro F1 các transition fingerprints thuộc flow theo `source_flow_id`. |
| **ordering_accuracy** | Tỉ lệ cặp thứ tự GT được pred `ordered_state_ids` tuân thủ. |
| **Branch macros** | So khớp tập `(outcome_type, to_state)` cho các `GroundTruthBranchGroup` có ≥ 2 nhánh (xem [`branch_matcher.py`](evaluator/branch_matcher.py)). |
| **invalid_transition_count / invalid_flow_rate** | Tham chiếu state không tồn tại trong GT/catalog footprint. |

---

## Cách đọc báo cáo

Markdown (`evaluation_report.md`) các section:

1. **Metrics** — bảng transition / flow / branch / error counts.  
2. **Transition Confusion** — TP/FP/FN strict + relaxed, sample strict rows.  
3. **Branch Detection** — chi tiết từng branch cluster + tags.  
4. **Ordering** — GT vs pred order string + điểm ordering.  
5. **Error Breakdown** — phân nhóm counts từ `analyze_errors`.  
6. **False Positives** / **False Negatives**.  
7. **Sample transition verdicts** — QA nhanh.

**CSV**: `evaluation_summary.csv` và batch copy dùng cùng header (xem [`evaluator/report_writer.py`](evaluator/report_writer.py) constants `CSV_HEADER_ROW`).
