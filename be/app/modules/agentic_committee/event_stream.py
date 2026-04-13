from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from app.core.config import settings


@dataclass
class _RequestStream:
    request_id: str
    batch_id: str | None = None
    next_sequence: int = 1
    completed: bool = False
    status: str = "running"
    events: deque[dict[str, Any]] = field(default_factory=deque)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CommitteeDebateEventStream:
    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_requests: int,
        max_events_per_request: int,
    ):
        self._ttl_seconds = max(60, ttl_seconds)
        self._max_requests = max(10, max_requests)
        self._max_events_per_request = max(50, max_events_per_request)
        self._streams: dict[str, _RequestStream] = {}
        self._lock = Lock()

    def register_request(
        self,
        *,
        request_id: str,
        batch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_request_id = self._safe_str(request_id)
        if not normalized_request_id:
            return

        now = self._utcnow()
        with self._lock:
            self._prune_locked(now)
            stream = self._streams.get(normalized_request_id)

            if stream is None:
                stream = self._create_stream_locked(
                    request_id=normalized_request_id,
                    batch_id=batch_id,
                    now=now,
                )
            else:
                # Treat an explicit register as the start of a fresh run.
                stream.events.clear()
                stream.next_sequence = 1
                stream.completed = False
                stream.status = "running"
                stream.updated_at = now
                stream.batch_id = self._safe_str(batch_id) or stream.batch_id

            start_metadata = dict(metadata or {})
            start_metadata["phase"] = "request_registered"
            self._append_event_locked(
                stream=stream,
                timestamp=now,
                event_type="stream_registered",
                role="system",
                message="Debate stream is live for this analyze request.",
                scenario_id=None,
                metadata=start_metadata,
            )

    def publish_log_event(self, event_payload: dict[str, Any], *, level: str | None = None) -> None:
        normalized_request_id = self._safe_str(event_payload.get("request_id"))
        if not normalized_request_id:
            return

        now = self._utcnow()
        with self._lock:
            self._prune_locked(now)
            stream = self._streams.get(normalized_request_id)
            if stream is None:
                stream = self._create_stream_locked(
                    request_id=normalized_request_id,
                    batch_id=self._safe_str(event_payload.get("batch_id")),
                    now=now,
                )

            event_type = self._safe_str(event_payload.get("event_type")) or "committee_event"
            role = self._resolve_role(event_type, event_payload)
            message = self._resolve_message(event_type, event_payload)
            timestamp = self._safe_str(event_payload.get("timestamp")) or now.isoformat()
            scenario_id = self._safe_str(event_payload.get("scenario_id"))

            metadata = dict(event_payload)
            if level:
                metadata["level"] = level

            self._append_event_locked(
                stream=stream,
                timestamp=timestamp,
                event_type=event_type,
                role=role,
                message=message,
                scenario_id=scenario_id,
                metadata=metadata,
            )

    def publish_system_event(
        self,
        *,
        request_id: str,
        batch_id: str | None = None,
        event_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        scenario_id: str | None = None,
    ) -> None:
        normalized_request_id = self._safe_str(request_id)
        if not normalized_request_id:
            return

        now = self._utcnow()
        with self._lock:
            self._prune_locked(now)
            stream = self._streams.get(normalized_request_id)
            if stream is None:
                stream = self._create_stream_locked(
                    request_id=normalized_request_id,
                    batch_id=batch_id,
                    now=now,
                )

            self._append_event_locked(
                stream=stream,
                timestamp=now,
                event_type=event_type,
                role="system",
                message=message,
                scenario_id=self._safe_str(scenario_id),
                metadata=dict(metadata or {}),
            )

    def mark_terminal(
        self,
        *,
        request_id: str,
        batch_id: str | None = None,
        status: str,
        reason: str | None = None,
    ) -> None:
        normalized_request_id = self._safe_str(request_id)
        if not normalized_request_id:
            return

        normalized_status = "failed" if str(status).strip().lower() == "failed" else "completed"
        now = self._utcnow()

        with self._lock:
            self._prune_locked(now)
            stream = self._streams.get(normalized_request_id)
            if stream is None:
                stream = self._create_stream_locked(
                    request_id=normalized_request_id,
                    batch_id=batch_id,
                    now=now,
                )

            if stream.completed and stream.status == normalized_status:
                return

            stream.completed = True
            stream.status = normalized_status
            if batch_id:
                stream.batch_id = self._safe_str(batch_id) or stream.batch_id

            terminal_message = (
                "Debate stream completed successfully."
                if normalized_status == "completed"
                else "Debate stream ended with a failure."
            )
            if reason:
                terminal_message = f"{terminal_message} Reason: {reason}"

            self._append_event_locked(
                stream=stream,
                timestamp=now,
                event_type="stream_terminal",
                role="system",
                message=terminal_message,
                scenario_id=None,
                metadata={
                    "status": normalized_status,
                    "reason": reason,
                },
            )

    def read_events(self, *, request_id: str, since_seq: int, limit: int) -> dict[str, Any]:
        normalized_request_id = self._safe_str(request_id)
        if not normalized_request_id:
            raise KeyError("request_id is required")

        requested_limit = max(1, limit)
        normalized_since_seq = max(0, since_seq)

        now = self._utcnow()
        with self._lock:
            self._prune_locked(now)
            stream = self._streams.get(normalized_request_id)
            if stream is None:
                raise KeyError(f"request stream not found: {normalized_request_id}")

            selected: list[dict[str, Any]] = []
            for event in stream.events:
                if int(event.get("sequence", 0)) <= normalized_since_seq:
                    continue
                selected.append(dict(event))
                if len(selected) >= requested_limit:
                    break

            next_seq = normalized_since_seq
            if selected:
                next_seq = int(selected[-1]["sequence"])
            elif stream.events:
                next_seq = min(
                    normalized_since_seq,
                    int(stream.events[-1].get("sequence", normalized_since_seq)),
                )

            return {
                "request_id": stream.request_id,
                "batch_id": stream.batch_id,
                "next_seq": next_seq,
                "completed": stream.completed,
                "status": stream.status,
                "events": selected,
            }

    def _create_stream_locked(
        self,
        *,
        request_id: str,
        batch_id: str | None,
        now: datetime,
    ) -> _RequestStream:
        self._evict_if_needed_locked()
        stream = _RequestStream(
            request_id=request_id,
            batch_id=self._safe_str(batch_id),
            updated_at=now,
        )
        self._streams[request_id] = stream
        return stream

    def _append_event_locked(
        self,
        *,
        stream: _RequestStream,
        timestamp: datetime | str,
        event_type: str,
        role: str,
        message: str,
        scenario_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        sequence = stream.next_sequence
        stream.next_sequence += 1
        stream.updated_at = self._utcnow()

        if isinstance(timestamp, datetime):
            timestamp_value = timestamp.astimezone(timezone.utc).isoformat()
        else:
            timestamp_value = str(timestamp)

        event = {
            "event_id": f"{stream.request_id}:{sequence}",
            "sequence": sequence,
            "timestamp": timestamp_value,
            "request_id": stream.request_id,
            "batch_id": stream.batch_id,
            "scenario_id": scenario_id,
            "role": role,
            "event_type": event_type,
            "message": message,
            "metadata": metadata,
        }

        stream.events.append(event)
        while len(stream.events) > self._max_events_per_request:
            stream.events.popleft()

    def _prune_locked(self, now: datetime) -> None:
        expiration_cutoff = now - timedelta(seconds=self._ttl_seconds)

        expired_request_ids = [
            request_id
            for request_id, stream in self._streams.items()
            if stream.updated_at < expiration_cutoff
        ]
        for request_id in expired_request_ids:
            self._streams.pop(request_id, None)

        self._evict_if_needed_locked()

    def _evict_if_needed_locked(self) -> None:
        if len(self._streams) < self._max_requests:
            return

        sorted_ids = sorted(
            self._streams,
            key=lambda request_id: self._streams[request_id].updated_at,
        )

        while len(self._streams) >= self._max_requests and sorted_ids:
            self._streams.pop(sorted_ids.pop(0), None)

    @staticmethod
    def _resolve_role(event_type: str, payload: dict[str, Any]) -> str:
        direct_role = str(payload.get("role", "")).strip().lower()
        if direct_role in {"ba", "qa", "ux", "judge", "system"}:
            return direct_role

        if event_type.startswith("judge") or event_type.startswith("finalize"):
            return "judge"
        if event_type.startswith("specialist"):
            return "specialist"
        return "system"

    def _resolve_message(self, event_type: str, payload: dict[str, Any]) -> str:
        current_round = payload.get("current_round")
        role = str(payload.get("role", "")).strip().upper()
        scenario_id = self._safe_str(payload.get("scenario_id"))

        if event_type == "scenario_start":
            return f"Debate started for scenario {scenario_id or 'unknown'}."

        if event_type == "round_start":
            return f"Round {current_round} started."

        if event_type == "specialist_request":
            return f"{role or 'SPECIALIST'} is preparing round {current_round} feedback."

        if event_type == "specialist_response":
            rationale = str(payload.get("rationale", "")).strip()
            score = payload.get("score")
            if rationale:
                if score is None:
                    return f"{role or 'SPECIALIST'}: {rationale}"
                return f"{role or 'SPECIALIST'} scored {score}/10. {rationale}"
            if score is None:
                return f"{role or 'SPECIALIST'} submitted a response."
            return f"{role or 'SPECIALIST'} scored {score}/10."

        if event_type == "judge_round_result":
            reason = str(payload.get("convergence_reason", "")).strip()
            if payload.get("is_converged"):
                return reason or "Judge marked the discussion as converged."
            return reason or "Judge requested another debate round."

        if event_type == "finalize_result":
            final_payload = payload.get("final_payload")
            if isinstance(final_payload, dict):
                summary = str(final_payload.get("conflict_resolution_summary", "")).strip()
                if summary:
                    return summary
            return "Judge finalized the committee decision."

        if event_type == "scenario_completed":
            return f"Scenario {scenario_id or 'unknown'} completed."

        if event_type.startswith("fallback"):
            return str(payload.get("reason", "")).strip() or "Fallback path activated."

        return event_type.replace("_", " ").strip().capitalize() + "."

    @staticmethod
    def _safe_str(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if len(text) > 160:
            return text[:160]
        return text

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)


committee_debate_event_stream = CommitteeDebateEventStream(
    ttl_seconds=settings.COMMITTEE_EVENT_STREAM_TTL_SECONDS,
    max_requests=settings.COMMITTEE_EVENT_STREAM_MAX_REQUESTS,
    max_events_per_request=settings.COMMITTEE_EVENT_STREAM_MAX_EVENTS_PER_REQUEST,
)
