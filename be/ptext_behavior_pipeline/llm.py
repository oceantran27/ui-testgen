"""Minimal OpenAI callers for P-TEXT prompts (no dependency on app OpenAIService prompts)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError

from ptext_behavior_pipeline.config import DEFAULT_MODEL, STAGE_A_PROMPT, STAGE_B_PROMPT, STAGE_C_PROMPT

logger = logging.getLogger(__name__)

_MIME_BY_EXT: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
}


def _read_prompt(path: Path) -> str:
    if not path.is_file():
        raise AIProcessingError(f"P-TEXT prompt missing: {path}")
    return path.read_text(encoding="utf-8")


def _mime_for_path(image_path: str) -> str:
    ext = Path(image_path).suffix.lower().lstrip(".")
    return _MIME_BY_EXT.get(ext, "image/jpeg")


class PtextOpenAIClient:
    """Stage B (vision JSON), Stage C (text JSON), Stage A (text-only JSON array)."""

    def __init__(self, model: str | None = None) -> None:
        if not settings.OPENAI_API_KEY:
            raise AIProcessingError("OPENAI_API_KEY is not configured in settings")
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model or DEFAULT_MODEL
        self._prompt_b = _read_prompt(STAGE_B_PROMPT)
        self._prompt_c = _read_prompt(STAGE_C_PROMPT)
        self._prompt_a = _read_prompt(STAGE_A_PROMPT)

    def _encode_image(self, image_path: str) -> str:
        try:
            data = Path(image_path).read_bytes()
        except OSError as exc:
            raise AIProcessingError(f"Failed to read image file: {exc}") from exc
        return base64.b64encode(data).decode("utf-8")

    def stage_b_vision_raw(self, image_path: str) -> str:
        b64 = self._encode_image(image_path)
        mime = _mime_for_path(image_path)
        user_text = (
            "Analyze this UI screenshot and output the UI hierarchy JSON exactly as specified "
            "in the system instructions (include P-TEXT blocks). Return exactly one JSON object. "
            "Do not include markdown, code fences, or extra text."
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._prompt_b},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        if not content.strip():
            raise AIProcessingError("Empty response from OpenAI (Stage B)")
        logger.debug("Stage B raw length: %s", len(content))
        return content

    def stage_c_text_raw(self, hierarchy_minified_json: str) -> str:
        user_text = (
            "UI hierarchy JSON from Stage B (sole source of truth for visible UI wording):\n"
            f"{hierarchy_minified_json}\n\n"
            "Produce the Stage C BDD bundle JSON per the system instructions. "
            "Return exactly one JSON object without markdown or code fences."
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._prompt_c},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        if not content.strip():
            raise AIProcessingError("Empty response from OpenAI (Stage C)")
        logger.debug("Stage C raw length: %s", len(content))
        return content

    def stage_a_text_raw(self, captures_bundle_json_minified: str) -> str:
        user_text = (
            "captures_bundle JSON (array of captures; order is NOT journey order):\n"
            f"{captures_bundle_json_minified}\n\n"
            "Return exactly one JSON object with key `flows` whose value is the array described in the system instructions."
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._prompt_a},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        if not content.strip():
            raise AIProcessingError("Empty response from OpenAI (Stage A)")
        logger.debug("Stage A raw length: %s", len(content))
        return content
