"""
Strategy Interface — abstract base class and shared data contracts.

All concrete song-generation strategies (mock, Suno API, or any future
provider) inherit from :class:`SongGeneratorStrategy` and exchange data
using :class:`GenerationRequest` / :class:`GenerationResult` so that the
service layer does not depend on any vendor-specific request/response
shape.

Design notes
------------
* ``generate(request)`` submits a new generation attempt and returns a
  ``GenerationResult`` that *always* carries a ``task_id`` — this is the
  value the caller stores on ``GenerationJob`` (Exercise 4 §4.3 item 2).
* ``get_status(task_id)`` performs a follow-up lookup (polling) and
  returns a fresh ``GenerationResult``. Strategies that complete
  synchronously (Mock) simply return their cached result.
* A ``StrategyStatus`` enum is used internally so the layer above the
  strategies does not have to understand Suno's ``TEXT_SUCCESS`` /
  ``FIRST_SUCCESS`` vocabulary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class StrategyStatus(str, Enum):
    """
    Provider-agnostic status vocabulary used by strategies.

    The service layer maps these values to the domain
    :class:`music.models.GenerationStatus` enum when updating
    ``GenerationJob`` / ``Song`` records.
    """
    PENDING = "PENDING"        # accepted by provider, not started
    PROCESSING = "PROCESSING"  # actively generating (any intermediate state)
    SUCCESS = "SUCCESS"        # final audio is available
    FAILED = "FAILED"          # provider reported an error / gave up


@dataclass(frozen=True)
class GenerationRequest:
    """
    Immutable input passed to a strategy's ``generate()`` method.

    Mirrors the form fields the CITHARA user fills in (SRS §4.2 /
    FR-07) but is intentionally a plain Python object — strategies
    never import Django models, which keeps the Strategy layer
    reusable and easy to test.
    """
    prompt_text: str
    title: str = ""
    genre: str = ""
    voice: Optional[str] = None
    occasion: Optional[str] = None
    mood: Optional[str] = None
    # Free-form hints that some providers accept (e.g. instrumental flag).
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """
    Output returned from every strategy call.

    Attributes
    ----------
    task_id:
        Unique identifier for this generation attempt. For Suno this is
        the server-assigned ``taskId``; for the Mock strategy it is a
        locally generated UUID. Persisted on ``GenerationJob`` so the
        service layer can later poll for progress.
    status:
        Current :class:`StrategyStatus`.
    progress:
        Integer percentage (0–100). Strategies that do not expose
        progress should report 0 for PENDING / PROCESSING and 100 for
        SUCCESS.
    audio_url:
        URL of the generated audio file once available.
    duration:
        Human-readable duration string (e.g. ``"3:24"``) when known.
    error_message:
        Populated when ``status == FAILED``.
    strategy_name:
        Name of the strategy that produced this result. Useful for
        logging / debugging when multiple strategies are wired up.
    raw:
        Vendor-specific payload returned by the provider. Kept for
        observability; the service layer should not parse it.
    """
    task_id: str
    status: StrategyStatus
    progress: int = 0
    audio_url: Optional[str] = None
    duration: Optional[str] = None
    error_message: Optional[str] = None
    strategy_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        """True when the generation has reached a final state."""
        return self.status in (StrategyStatus.SUCCESS, StrategyStatus.FAILED)


class SongGeneratorStrategy(ABC):
    """
    Abstract base class defining the Strategy Pattern contract.

    Every concrete strategy (Mock / Suno / future providers) must
    implement :meth:`generate` and :meth:`get_status`. Consumers only
    depend on this interface — they never instantiate concrete
    strategies directly, which keeps strategy selection isolated to
    :mod:`music.generation.factory`.
    """

    #: Short identifier used by the factory / logs (e.g. "mock", "suno").
    name: str = "abstract"

    @abstractmethod
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """
        Submit a new generation attempt.

        Must return a :class:`GenerationResult` whose ``task_id`` is
        non-empty — the caller is expected to persist this value.
        """
        raise NotImplementedError

    @abstractmethod
    def get_status(self, task_id: str) -> GenerationResult:
        """
        Look up the current state of an already-submitted task.

        Strategies that complete synchronously are free to return a
        cached result; strategies backed by an external service should
        perform a fresh network call.
        """
        raise NotImplementedError

    # Convenience method so callers can write ``str(strategy)`` in logs.
    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<{self.__class__.__name__} name={self.name!r}>"
