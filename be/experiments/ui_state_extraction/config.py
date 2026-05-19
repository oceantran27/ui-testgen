"""Experiment configuration for ui_state_extraction (module 1)."""

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent

# Experiment package root (for portable manifest paths).
PACKAGE_ROOT = _PACKAGE_ROOT

# Set to your dataset root (local path or http(s) URL to a directory or single image).
IMAGE_ROOT_URL_OR_PATH: str = r"C:\Users\daidu\Desktop\DataExp\DemoAuth"

RAW_OUTPUT_DIR: Path = _PACKAGE_ROOT / "raw_outputs"
TEMP_GROUND_TRUTH_DIR: Path = _PACKAGE_ROOT / "temp_ground_truth"
REPORT_DIR: Path = _PACKAGE_ROOT / "reports"

ALLOWED_IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")
PROMPT_NAME: str = "prompt_joint_screen_understanding_v1"
PROMPT_FILE_FALLBACK: str = "prompt_joint_screen_understanding_v1.txt"

MAX_CONCURRENCY: int = 3
OVERWRITE_RAW_OUTPUT: bool = False

# After discovery (sorted by relative_path): take only the first N images. 0 = process all.
# Useful for smoke tests (e.g. MAX_IMAGES_TO_PROCESS = 5).
MAX_IMAGES_TO_PROCESS: int = 0

# Match joint_screen_understanding_service: base prompt + Phase 2 taxonomy suffix.
MATCH_JOINT_SERVICE_SYSTEM_PROMPT: bool = True

# If True, upload bytes to storage_service and pass storage_uri (Option A).
USE_STORAGE_UPLOAD: bool = False

# When slug(image path) exceeds this length, use stem slug + short hash suffix.
IMAGE_ID_MAX_LENGTH: int = 120

EXPERIMENT_NAME: str = "ui_state_extraction"
RAW_OUTPUT_SCHEMA_VERSION: str = "experiment_raw_output_v1"
MANIFEST_SCHEMA_VERSION: str = "raw_output_manifest_v1"

TEMP_GT_SCHEMA_VERSION: str = "ui_state_extraction_temp_ground_truth_v1"
TEMP_GT_MANIFEST_SCHEMA_VERSION: str = "temp_ground_truth_manifest_v1"

# Structured debug log (module 2 / 3 JSONL under pipeline_debug/)
EXPERIMENT_DEBUG_LOG_ENABLED: bool = False
EXPERIMENT_DEBUG_LOG_DIR: Path = REPORT_DIR / "pipeline_debug"
EXPERIMENT_DEBUG_LOG_VERBOSE: bool = False

# Module 2: skip existing .temp_gt.json unless True
OVERWRITE_TEMP_GROUND_TRUTH: bool = False

# Include model id → gt id maps on each temp GT file (larger JSON)
INCLUDE_DEBUG_ID_MAPS: bool = False

# Module 3: evaluation
EVALUATION_REPORT_DIR: Path = _PACKAGE_ROOT / "evaluation_reports"
EVALUATION_SUMMARY_SCHEMA_VERSION: str = "ui_state_extraction_evaluation_summary_v2"

TEXT_MATCH_MODE: str = "contains"
TEXT_MATCH_CASE_INSENSITIVE: bool = True

GROUP_MATCH_JACCARD_THRESHOLD: float = 0.6
INTENT_MATCH_STRATEGY: str = "intent_kind_plus_commit_or_primary_action"

EVALUATE_UNRESOLVED_GROUPS: bool = False
EVALUATE_SELECTION_OPTIONS: bool = False

INCLUDE_DEBUG_MATCH_TABLES: bool = True

