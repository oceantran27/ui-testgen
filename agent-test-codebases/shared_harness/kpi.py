from __future__ import annotations

import json
import importlib
import math
import sys
from pathlib import Path
from statistics import mean
from typing import Any


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # Lightweight approximation suitable for relative benchmarking.
    return math.ceil(len(text) / 4)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    # Conservative defaults; set to 0 if model pricing is unknown.
    assumed_rates_per_1m = {
        "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
        "gemini-1.5-flash": {"input": 0.35, "output": 1.05},
    }
    rates = assumed_rates_per_1m.get(model, {"input": 0.0, "output": 0.0})
    return round(
        ((input_tokens / 1_000_000) * rates["input"]) + ((output_tokens / 1_000_000) * rates["output"]),
        8,
    )


def latency_summary(latencies_ms: list[int]) -> dict[str, float]:
    if not latencies_ms:
        return {"p50": 0.0, "p95": 0.0, "avg": 0.0}

    ordered = sorted(latencies_ms)

    def percentile(values: list[int], pct: float) -> float:
        if not values:
            return 0.0
        index = max(0, min(len(values) - 1, int(math.ceil((pct / 100.0) * len(values)) - 1)))
        return float(values[index])

    return {
        "p50": percentile(ordered, 50.0),
        "p95": percentile(ordered, 95.0),
        "avg": float(mean(ordered)),
    }


def traceability_coverage(stage_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = stage_name.strip().lower()

    if normalized == "visual_parser":
        groups = payload.get("visual_groups", [])
        elements = [
            element
            for group in groups
            if isinstance(group, dict)
            for element in group.get("elements", [])
            if isinstance(element, dict)
        ]
        total = len(elements)
        traced = sum(1 for item in elements if str(item.get("id", "")).strip())
        ratio = float(traced / total) if total else 1.0
        return {"total_items": total, "traced_items": traced, "coverage": ratio}

    if normalized == "business_analyst":
        rules_container = payload.get("business_rules", {})
        keys = ("Field_Level_Rules", "State_Rules", "Workflow_Rules", "Validation_Rules")
        rules = [
            rule
            for key in keys
            for rule in rules_container.get(key, [])
            if isinstance(rule, dict)
        ]
        total = len(rules)
        traced = sum(1 for item in rules if isinstance(item.get("element_ids", []), list) and len(item["element_ids"]) > 0)
        ratio = float(traced / total) if total else 1.0
        return {"total_items": total, "traced_items": traced, "coverage": ratio}

    scenarios = payload.get("scenarios", [])
    valid_scenarios = [item for item in scenarios if isinstance(item, dict)]
    total = len(valid_scenarios)
    if total == 0:
        return {"total_items": 0, "traced_items": 0, "coverage": 1.0}

    traced = 0
    for item in valid_scenarios:
        has_refs = isinstance(item.get("referenced_element_ids", []), list) and len(item["referenced_element_ids"]) > 0
        has_rules = isinstance(item.get("source_rules", []), list) and len(item["source_rules"]) > 0
        if has_refs and has_rules:
            traced += 1
    return {"total_items": total, "traced_items": traced, "coverage": float(traced / total)}


def load_ground_truth_for_image(ground_truth_file: Path, image_path: Path) -> list[str]:
    if not ground_truth_file.exists():
        return []

    image_stem = image_path.stem
    try:
        image_id = int(image_stem)
    except Exception:
        return []

    try:
        raw = json.loads(ground_truth_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(raw, list):
        return []

    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            if int(item.get("id")) == image_id:
                values = item.get("ground_truth", [])
                if isinstance(values, list):
                    return [str(v).strip() for v in values if str(v).strip()]
        except Exception:
            continue
    return []


def semantic_precision_recall(predicted_goals: list[str], ground_truth_goals: list[str]) -> dict[str, Any]:
    if not predicted_goals and not ground_truth_goals:
        return {
            "precision": 1.0,
            "recall": 1.0,
            "hallucination_rate": 0.0,
            "available": True,
        }

    if not predicted_goals:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "hallucination_rate": 0.0,
            "available": True,
        }

    try:
        be_dir = Path(__file__).resolve().parents[2] / "be"
        if str(be_dir) not in sys.path:
            sys.path.insert(0, str(be_dir))

        evaluation_module = importlib.import_module("evaluation.main")
        sentence_transformers_module = importlib.import_module("sentence_transformers")
        perform_evaluation = getattr(evaluation_module, "perform_evaluation")
        sentence_transformer_type = getattr(sentence_transformers_module, "SentenceTransformer")

        model = sentence_transformer_type("BAAI/bge-large-en-v1.5")
        result = perform_evaluation({"ground_truth": ground_truth_goals, "user_goals": predicted_goals}, model=model)
        precision = 1.0 - float(result.get("percent_hallucination", 0.0))
        recall = float(result.get("percent_match", 0.0))
        hallucination_rate = float(result.get("percent_hallucination", 0.0))
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "hallucination_rate": round(hallucination_rate, 4),
            "available": True,
        }
    except Exception as exc:
        return {
            "precision": None,
            "recall": None,
            "hallucination_rate": None,
            "available": False,
            "reason": str(exc),
        }
