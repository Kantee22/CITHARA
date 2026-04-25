"""
Suno API Generator Strategy — integration with sunoapi.org.

Satisfies Exercise 4 §4.3. The strategy performs two HTTP calls:

1. ``POST /api/v1/generate`` — submits a new generation task and
   returns ``taskId``.
2. ``GET  /api/v1/generate/record-info?taskId=<id>`` — returns the
   latest status and, when ready, the generated audio URL(s).

Both endpoints authenticate with a Bearer token. The token is loaded
from ``settings.SUNO_API_KEY`` (sourced from the ``SUNO_API_KEY``
environment variable) and must never be committed to the repository —
see ``.env.example`` and README §"Where to put the Suno API key".

This module uses the ``requests`` library because it is the de-facto
standard for synchronous HTTP in Django projects. Callers that need
async support can wrap ``generate()`` / ``get_status()`` in
``asgiref.sync.sync_to_async``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover - requests is in requirements.txt
    requests = None  # type: ignore[assignment]

from .base import (
    GenerationRequest,
    GenerationResult,
    SongGeneratorStrategy,
    StrategyStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------
# Suno exposes a richer vocabulary than the CITHARA domain needs. The
# mapping below collapses everything that still represents "work in
# progress" into PROCESSING, and everything that signals failure into
# FAILED. This keeps the service layer simple.
_SUNO_STATUS_MAP: Dict[str, StrategyStatus] = {
    "PENDING":       StrategyStatus.PENDING,
    "QUEUED":        StrategyStatus.PENDING,
    "TEXT_SUCCESS":  StrategyStatus.PROCESSING,
    "FIRST_SUCCESS": StrategyStatus.PROCESSING,
    "PROCESSING":    StrategyStatus.PROCESSING,
    "SUCCESS":       StrategyStatus.SUCCESS,
    "COMPLETE":      StrategyStatus.SUCCESS,
    "FAILED":        StrategyStatus.FAILED,
    "ERROR":         StrategyStatus.FAILED,
    "CANCELED":      StrategyStatus.FAILED,
    "SENSITIVE_WORD_ERROR": StrategyStatus.FAILED,
}


class SunoStrategyError(RuntimeError):
    """Raised when the Suno API responds with a non-recoverable error."""


class SunoSongGeneratorStrategy(SongGeneratorStrategy):
    """
    Calls the public ``sunoapi.org`` service to generate music.

    Parameters
    ----------
    api_key:
        Bearer token issued by sunoapi.org. Required.
    base_url:
        Override for the API base URL. Defaults to the production
        endpoint documented in the exercise brief.
    timeout:
        Per-request timeout in seconds (default: 30).
    model:
        The Suno model to request. Defaults to ``"V4"`` which is
        suitable for the default free-tier behavior; can be tuned via
        Django settings if needed.
    """

    name = "suno"

    DEFAULT_BASE_URL = "https://api.sunoapi.org/api/v1"
    GENERATE_PATH = "/generate"
    RECORD_INFO_PATH = "/generate/record-info"

    #: Suno rejects requests without a ``callBackUrl`` (HTTP 400
    #: "Please enter callBackUrl."). The URL does not have to be
    #: reachable — Suno only validates that the field is present —
    #: but supplying a real webhook here would let Suno notify us
    #: instead of having to poll. We keep polling for simplicity and
    #: ship a documented placeholder by default.
    DEFAULT_CALLBACK_URL = "https://example.com/cithara/suno-callback"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: int = 30,
        model: str = "V4",
        callback_url: Optional[str] = None,
    ) -> None:
        if requests is None:
            raise RuntimeError(
                "The 'requests' package is required for SunoSongGeneratorStrategy. "
                "Install it with: pip install requests"
            )
        if not api_key:
            raise ValueError(
                "SUNO_API_KEY is empty. Set the SUNO_API_KEY environment "
                "variable or configure settings.SUNO_API_KEY before using "
                "the 'suno' strategy."
            )
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.model = model
        self.callback_url = callback_url or self.DEFAULT_CALLBACK_URL

    # ------------------------------------------------------------------
    # Strategy interface
    # ------------------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = self._build_payload(request)
        url = f"{self.base_url}{self.GENERATE_PATH}"
        logger.info("Suno: POST %s (title=%r genre=%r)",
                    url, request.title, request.genre)

        response = requests.post(
            url, json=payload, headers=self._headers(), timeout=self.timeout
        )
        body = self._safe_json(response)

        if response.status_code >= 400:
            raise SunoStrategyError(
                f"Suno generate failed: HTTP {response.status_code} — "
                f"{body.get('msg') or body.get('message') or response.text[:200]}"
            )

        task_id = self._extract_task_id(body)
        if not task_id:
            raise SunoStrategyError(
                f"Suno generate response did not contain a taskId: {body!r}"
            )

        # Suno returns only the task id on submit; status is unknown
        # until the caller polls record-info. Start at PENDING.
        return GenerationResult(
            task_id=task_id,
            status=StrategyStatus.PENDING,
            progress=0,
            strategy_name=self.name,
            raw=body,
        )

    def get_status(self, task_id: str) -> GenerationResult:
        if not task_id:
            raise ValueError("task_id is required")

        url = f"{self.base_url}{self.RECORD_INFO_PATH}"
        logger.info("Suno: GET %s?taskId=%s", url, task_id)

        response = requests.get(
            url,
            headers=self._headers(),
            params={"taskId": task_id},
            timeout=self.timeout,
        )
        body = self._safe_json(response)

        if response.status_code >= 400:
            raise SunoStrategyError(
                f"Suno record-info failed: HTTP {response.status_code} — "
                f"{body.get('msg') or body.get('message') or response.text[:200]}"
            )

        return self._parse_record_info(task_id, body)

    # ------------------------------------------------------------------
    # Request construction
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        """Bearer-token headers used by every call (Exercise 4 §4.3)."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _build_payload(self, request: GenerationRequest) -> Dict[str, Any]:
        """
        Assemble the JSON body for ``POST /generate``.

        The style string is built from the CITHARA domain fields
        (genre / mood / occasion / voice) so the provider receives a
        compact, human-readable description without the service layer
        having to know Suno-specific field names.
        """
        style_parts = [p for p in [
            request.genre,
            request.mood,
            request.occasion,
            f"{request.voice} vocal" if request.voice else None,
        ] if p]
        style = ", ".join(style_parts)

        payload: Dict[str, Any] = {
            "prompt": request.prompt_text,
            "title": request.title or "Untitled",
            "style": style,
            "customMode": True,
            "instrumental": request.extra.get("instrumental", False),
            "model": request.extra.get("model", self.model),
            # Suno enforces this field — see DEFAULT_CALLBACK_URL note.
            # A request-level override (request.extra) wins over the
            # strategy-level default so callers can plug in a real
            # webhook URL on a per-request basis.
            "callBackUrl": request.extra.get("callBackUrl", self.callback_url),
        }
        return payload

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_json(response: "requests.Response") -> Dict[str, Any]:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}
        except ValueError:
            return {}

    @staticmethod
    def _extract_task_id(body: Dict[str, Any]) -> Optional[str]:
        """
        Pull the ``taskId`` out of a ``/generate`` response.

        Suno nests the id under ``data.taskId`` but older/alt docs
        return it at the top level — we accept either.
        """
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        return (
            data.get("taskId")
            or data.get("task_id")
            or body.get("taskId")
            or body.get("task_id")
        )

    def _parse_record_info(self, task_id: str, body: Dict[str, Any]) -> GenerationResult:
        """
        Translate a ``/generate/record-info`` payload into a
        :class:`GenerationResult`.

        The real API returns a nested ``data`` object containing a
        ``status`` field plus a ``response.sunoData`` list with the
        generated tracks. We defensively walk the tree so the parser
        survives minor schema drift.
        """
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        raw_status = str(data.get("status") or body.get("status") or "PENDING").upper()
        status = _SUNO_STATUS_MAP.get(raw_status, StrategyStatus.PROCESSING)

        # Locate the first audio track, if any.
        tracks = []
        resp = data.get("response") or {}
        if isinstance(resp, dict):
            tracks = resp.get("sunoData") or resp.get("clips") or []
        elif isinstance(data.get("sunoData"), list):
            tracks = data["sunoData"]

        audio_url: Optional[str] = None
        duration: Optional[str] = None
        if tracks and isinstance(tracks[0], dict):
            first = tracks[0]
            audio_url = (
                first.get("audioUrl")
                or first.get("audio_url")
                or first.get("streamAudioUrl")
            )
            raw_duration = first.get("duration")
            if raw_duration is not None:
                duration = self._format_duration(raw_duration)

        # Progress heuristic: no explicit field → derive from status.
        progress = {
            StrategyStatus.PENDING: 5,
            StrategyStatus.PROCESSING: 50,
            StrategyStatus.SUCCESS: 100,
            StrategyStatus.FAILED: 0,
        }[status]

        error_message: Optional[str] = None
        if status == StrategyStatus.FAILED:
            error_message = (
                data.get("errorMessage")
                or data.get("msg")
                or body.get("msg")
                or f"Suno reported status {raw_status}"
            )

        return GenerationResult(
            task_id=task_id,
            status=status,
            progress=progress,
            audio_url=audio_url,
            duration=duration,
            error_message=error_message,
            strategy_name=self.name,
            raw=body,
        )

    @staticmethod
    def _format_duration(value: Any) -> str:
        """Convert a duration (seconds, int/float, or string) to ``m:ss``."""
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return str(value)
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes}:{secs:02d}"
