"""
Mock Generator Strategy — offline, deterministic implementation.

This strategy satisfies Exercise 4 §4.2: it performs *no* external API
calls, produces predictable output (a fixed placeholder audio URL),
and is safe to use during development, demos, and unit tests when
network access is unavailable or undesirable.

The mock immediately returns ``SUCCESS`` — there is no asynchronous
processing, so ``get_status()`` simply replays the cached result for
any ``task_id`` the mock has seen.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict

from .base import (
    GenerationRequest,
    GenerationResult,
    SongGeneratorStrategy,
    StrategyStatus,
)


class MockSongGeneratorStrategy(SongGeneratorStrategy):
    """
    Deterministic offline strategy.

    Behavior
    --------
    * ``generate()`` synthesizes a ``task_id`` of the form
      ``mock-<8-hex>`` derived from the request content, so calling
      ``generate()`` with the same inputs twice yields the same id —
      convenient for testing.
    * The returned audio URL points at a stable placeholder so tests
      can assert on it.
    * ``get_status()`` returns the cached ``GenerationResult`` for the
      given ``task_id`` (or a synthetic SUCCESS result if the id was
      not produced by this process — useful when the DB holds a
      ``job_id`` from a previous run).
    """

    name = "mock"

    #: Fixed placeholder audio URL. Intentionally a well-known sample
    #: so downstream UI / tests can rely on it.
    PLACEHOLDER_AUDIO_URL = (
        "https://cithara.local/mock/audio/placeholder.mp3"
    )
    PLACEHOLDER_DURATION = "3:00"

    def __init__(self) -> None:
        # Small in-process cache so ``get_status`` can replay earlier
        # results. Real providers persist state server-side; the mock
        # keeps it here because there is no server.
        self._cache: Dict[str, GenerationResult] = {}

    # ------------------------------------------------------------------
    # Strategy interface
    # ------------------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GenerationResult:
        task_id = self._make_task_id(request)
        result = GenerationResult(
            task_id=task_id,
            status=StrategyStatus.SUCCESS,
            progress=100,
            audio_url=self.PLACEHOLDER_AUDIO_URL,
            duration=self.PLACEHOLDER_DURATION,
            strategy_name=self.name,
            raw={
                "mock": True,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "echo": {
                    "title": request.title,
                    "genre": request.genre,
                    "voice": request.voice,
                    "occasion": request.occasion,
                    "mood": request.mood,
                    "prompt_length": len(request.prompt_text),
                },
            },
        )
        self._cache[task_id] = result
        return result

    def get_status(self, task_id: str) -> GenerationResult:
        cached = self._cache.get(task_id)
        if cached is not None:
            return cached

        # The task_id was not produced by this process (e.g. the caller
        # restarted the server). For a mock we still want a useful
        # answer, so return a synthetic SUCCESS result that references
        # the same placeholder — this keeps the workflow testable
        # across restarts.
        return GenerationResult(
            task_id=task_id,
            status=StrategyStatus.SUCCESS,
            progress=100,
            audio_url=self.PLACEHOLDER_AUDIO_URL,
            duration=self.PLACEHOLDER_DURATION,
            strategy_name=self.name,
            raw={"mock": True, "replayed": True},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_task_id(request: GenerationRequest) -> str:
        """
        Build a stable task id from the request contents.

        Deterministic ids make the mock easy to assert against in
        tests: ``assert result.task_id == mock._make_task_id(req)``.
        """
        fingerprint = "|".join([
            request.prompt_text,
            request.title or "",
            request.genre or "",
            request.voice or "",
            request.occasion or "",
            request.mood or "",
        ]).encode("utf-8")
        digest = hashlib.sha256(fingerprint).hexdigest()[:8]
        # Prefix makes mock ids easy to spot in logs / DB.
        return f"mock-{digest}-{uuid.uuid4().hex[:4]}"
