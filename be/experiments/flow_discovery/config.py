"""Experiment configuration for flow_discovery (scaffold).

Sprint: short CLI — edit the ``CLI_*`` block below, then run commands without long flags
(e.g. ``python -m experiments.flow_discovery.cli build-compressed``).

Path strings are relative to this package directory (``flow_discovery/``) unless absolute.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_PACKAGE_ROOT = Path(__file__).resolve().parent

PACKAGE_ROOT = _PACKAGE_ROOT

EXPERIMENT_NAME = "flow_discovery"
DEFAULT_APP_ID = "demoauth"

RAW_OUTPUT_SCHEMA_VERSION = "raw_flow_discovery_experiment_v1"
GROUND_TRUTH_SCHEMA_VERSION = "ground_truth_flow_package_v2"
EVALUATION_SCHEMA_VERSION = "flow_discovery_evaluation_v2"

PROMPT_NAME = "prompt_global_flow_discovery"
PROMPT_VERSION = "v2"

DEFAULT_NODE_NAME_RAW_CAPTURE = "flow_discovery_raw_capture"

INPUT_BUILDER_AGENT_NAME = "experiment_joint_raw_to_compressed"
DEFAULT_RAW_JOINT_SUFFIX = ".raw.json"


# =============================================================================
# CLI defaults — chỉnh tại đây để chạy lệnh ngắn không cần nhiều argument
# =============================================================================

CLI_APP_ID: str = DEFAULT_APP_ID

# Thư mục làm việc chung (run-one, run-one-from-joint-raw, v.v.)
CLI_WORK_DIR: str = "outputs/cli_work/demoauth"

# --- input_builder → compressed catalog ---
CLI_RAW_JOINT_DIR: str = "fixtures/demoauth/raw_joint_outputs"
CLI_INPUT_BUILDER_OUT_DIR: str = "outputs/cli_work/demoauth/input_builder"
CLI_IMAGE_MAP_PATH: Optional[str] = "fixtures/demoauth/image_map.sample.json"
CLI_INPUT_BUILDER_STRICT: bool = False

# --- raw-capture ---
CLI_COMPRESSED_CATALOG_PATH: str = "fixtures/demoauth/compressed_catalog_package.json"
CLI_RAW_CAPTURE_OUTPUT_PATH: str = "outputs/cli_work/demoauth/raw_model_output.json"

# --- ground truth / evaluation (đường dẫn mẫu trỏ fixtures; đổi sang dataset thật khi cần) ---
CLI_GROUND_TRUTH_REVIEWED_PATH: Optional[str] = None
CLI_GT_CONVERT_RAW_OUTPUT: str = "fixtures/demoauth/raw_model_output.json"
CLI_GT_CONVERT_OUT: str = "outputs/cli_work/demoauth/ground_truth.draft.json"
CLI_GT_VALIDATE_INPUT: str = "fixtures/demoauth/ground_truth.reviewed.sample.json"
CLI_GT_VALIDATE_OUT: Optional[str] = None
CLI_EVAL_RAW_OUTPUT: str = "fixtures/demoauth/raw_model_output.json"
CLI_EVAL_GROUND_TRUTH: str = "fixtures/demoauth/ground_truth.reviewed.sample.json"
CLI_EVAL_OUT_DIR: str = "outputs/cli_work/demoauth/evaluation"

# --- batch (để trống manifest = bắt buộc truyền --manifest hoặc đặt path hợp lệ) ---
CLI_RUN_BATCH_MANIFEST: str = ""
CLI_RUN_BATCH_OUT_DIR: str = "outputs/cli_batch_out"
CLI_RUN_BATCH_FAIL_FAST: bool = False

CLI_BUILD_COMPRESSED_BATCH_MANIFEST: str = "fixtures/apps_manifest_joint_raw.json"
CLI_BUILD_COMPRESSED_BATCH_STRICT: bool = False

# --- model / prompt overrides (None = dùng production settings) ---
CLI_RUN_ID: Optional[str] = None
CLI_PROMPT_VERSION: Optional[str] = PROMPT_VERSION
CLI_PROMPT_NAME: Optional[str] = None
CLI_PROVIDER: Optional[str] = None
CLI_MODEL: Optional[str] = None
CLI_MAX_CATALOG_SCREENS: Optional[int] = None
CLI_SKIP_RAW_CAPTURE: bool = False
CLI_VALIDATE_CATALOG_SCREEN_COUNT: bool = True


def resolve_cli_path(rel_or_abs: Optional[str]) -> Optional[Path]:
    """Resolve a package-relative or absolute path string; empty/None → None."""
    if rel_or_abs is None:
        return None
    s = str(rel_or_abs).strip()
    if not s:
        return None
    p = Path(s)
    if p.is_absolute():
        return p.resolve()
    from experiments.flow_discovery.paths import resolve_path_under_package

    return resolve_path_under_package(s)
