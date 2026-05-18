from typing import Any, Dict, List
import re

def map_test_path(intent_type: str) -> str:
    normalized = (intent_type or "").strip().lower()
    mapping = {
        "positive": "happy_path",
        "negative": "negative_path",
        "validation": "validation_path",
        "navigation": "navigation_path",
        "recovery": "recovery_path",
        "registration": "registration_path",
        "access_control": "access_control_path",
        "data_entry": "data_entry_path",
    }
    return mapping.get(normalized, "unknown_path")

def format_action_step(action: Any) -> str:
    """Formats raw UI triggers into generic BDD actions (e.g. Click, Select, Enter)"""
    if not action:
        return ""

    if isinstance(action, dict):
        a_type = (action.get("action_type") or "click").lower()
        a_text = " ".join(action.get("text", []))
    else:
        a_type = (getattr(action, "action_type", "click") or "click").lower()
        a_text = " ".join(getattr(action, "text", []))

    if not a_text:
        return ""

    if a_type in ["select_option", "select", "option", "choice"]:
        return f"Select \"{a_text}\""
    elif a_type in ["input", "type", "fill", "enter"]:
        return f"Enter \"{a_text}\""
    elif a_type in ["commit", "confirm", "submit"]:
        return f"Confirm \"{a_text}\""
    else:
        return f"Click \"{a_text}\""

def select_distinguishing_evidence(node: Dict[str, Any]) -> List[str]:
    """
    Extracts minimal, distinguishing UI evidence for BDD assertions generically.
    Uses taxonomy from compressed_catalog (Agent 3.5 output).
    """
    txt = node.get("taxonomy", {})
    return txt.get("distinguishing_evidence") or []
