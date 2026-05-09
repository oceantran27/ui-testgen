import json
import logging
import re

logger = logging.getLogger(__name__)


def strip_json_comments(value: str) -> str:
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.DOTALL)
    value = re.sub(r"(^|\s)//.*$", "", value, flags=re.MULTILINE)
    return value


def remove_trailing_commas(value: str) -> str:
    return re.sub(r",\s*(?=[}\]])", "", value)


def _find_wrapped_json_block(value: str) -> str | None:
    lower = value.lower()

    fence_labeled = "```json"
    start = lower.find(fence_labeled)
    if start != -1:
        start += len(fence_labeled)
        end = lower.find("```", start)
        if end != -1:
            block = value[start:end].strip()
            if block:
                return block

    for_match = re.finditer(r"```(?:json)?\s*\n(.*?)```", value, flags=re.DOTALL | re.IGNORECASE)
    candidates: list[str] = []
    for match in for_match:
        content = match.group(1).strip()
        if content:
            candidates.append(content)

    jsonish = [c for c in candidates if (c.startswith("{") or c.startswith("[")) and ":" in c]
    if jsonish:
        return jsonish[-1]

    return None


def _find_balanced_json_object(value: str, start_idx: int) -> str | None:
    if start_idx == -1:
        return None

    depth = 0
    in_str = False
    esc = False

    for idx in range(start_idx, len(value)):
        ch = value[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return value[start_idx : idx + 1].strip()

    return None


def find_json_block(value: str) -> str | None:
    wrapped = _find_wrapped_json_block(value)
    if wrapped:
        return wrapped

    key = '"scenarios"'
    key_idx = value.find(key)
    if key_idx != -1:
        brace_positions = [
            match.start()
            for match in re.finditer(r"\{", value[: key_idx + 1])
        ]

        for start_idx in brace_positions:
            focused = _find_balanced_json_object(value, start_idx)
            if focused and key in focused:
                return focused

    return _find_balanced_json_object(value, value.find("{"))


def extract_and_minify_json(value: str) -> str | None:
    raw_json = find_json_block(value)
    candidate = raw_json if raw_json is not None else value.strip()
    cleaned = strip_json_comments(candidate)
    cleaned = remove_trailing_commas(cleaned)

    try:
        parsed = json.loads(cleaned)
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:
        logger.error("Failed to parse extracted JSON: %s", exc)
        return None
