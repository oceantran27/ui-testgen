"""Shared Gemini client + helpers using the google-genai SDK."""

from functools import lru_cache
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

from app.core.config import settings


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def default_generate_config(system_instruction: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
    )


def pil_image_to_part(image: Image.Image) -> types.Part:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")
