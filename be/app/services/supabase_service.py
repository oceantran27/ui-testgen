import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SupabaseService:
    def __init__(self):
        self.base_url = (settings.SUPABASE_URL or "").strip().rstrip("/")
        self.api_key = (settings.SUPABASE_KEY or "").strip()
        self.analysis_table = settings.SUPABASE_ANALYSIS_TABLE

    def is_ready(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _url(self, table: str) -> str:
        return f"{self.base_url}/rest/v1/{table}"

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: Any | None = None,
        prefer: str | None = None,
    ) -> Any:
        if not self.is_ready():
            raise ConnectionError("Supabase is not configured.")

        url = self._url(table)
        with httpx.Client(timeout=20.0) as client:
            response = client.request(
                method=method,
                url=url,
                headers=self._headers(prefer),
                params=params,
                json=json_data,
            )

        if response.status_code >= 400:
            logger.error("Supabase %s request failed (%s): %s", method, response.status_code, response.text)
            raise RuntimeError("Supabase request failed")

        if not response.text:
            return None
        return response.json()

    def create_analysis_record(self, image_url: str, user_goal: str) -> dict[str, Any] | None:
        payload = [{"image_url": image_url, "user_goal": user_goal}]
        data = self._request(
            "POST",
            self.analysis_table,
            json_data=payload,
            prefer="return=representation",
        )
        if isinstance(data, list) and data:
            return data[0]
        return None

    def get_analysis_records(self, skip: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        params = {
            "select": "*",
            "order": "created_at.desc",
            "offset": max(skip, 0),
            "limit": max(min(limit, 500), 1),
        }
        data = self._request("GET", self.analysis_table, params=params)
        if isinstance(data, list):
            return data
        return []

    def delete_analysis_record(self, record_id: int) -> dict[str, Any] | None:
        params = {
            "id": f"eq.{record_id}",
            "select": "*",
        }
        data = self._request(
            "DELETE",
            self.analysis_table,
            params=params,
            prefer="return=representation",
        )
        if isinstance(data, list) and data:
            return data[0]
        return None

    def delete_expired_analysis_records(self, retention_days: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()
        params = {
            "created_at": f"lt.{cutoff_iso}",
            "select": "*",
        }
        data = self._request(
            "DELETE",
            self.analysis_table,
            params=params,
            prefer="return=representation",
        )
        if isinstance(data, list):
            return data
        return []
