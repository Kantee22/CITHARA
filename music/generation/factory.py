"""
Strategy Factory — centralized selector for the active generator.

Exercise 4 §5 explicitly requires a *single* place where the
application decides which :class:`SongGeneratorStrategy` to use, so
that switching from the offline mock to the live Suno API (or adding a
new provider later) never involves touching the service layer, the
views, or the tests.

Selection rules
---------------
* Read ``settings.GENERATOR_STRATEGY`` — a short string (``"mock"`` or
  ``"suno"``). The Django setting in turn reads the environment
  variable ``GENERATOR_STRATEGY`` so ops can flip providers without a
  code change.
* Look the string up in :data:`STRATEGY_REGISTRY` — a plain dict keyed
  by strategy name. Adding a new provider is a one-line change here.
* Instantiate the matching strategy with the configuration it needs
  (e.g. ``SUNO_API_KEY`` for the Suno strategy).
* Unknown names raise :class:`ImproperlyConfigured` with the list of
  valid options so the error is immediately actionable.

Why a registry (not ``if/elif``)?
---------------------------------
The exercise brief warns against scattering ``if strategy == "mock":``
branches throughout the codebase. A dict-based registry makes the
rule explicit: the *only* way to expose a new provider is to register
it here. Application code always calls
:func:`get_generator_strategy` and never instantiates concrete
strategies directly.
"""

from __future__ import annotations

from typing import Callable, Dict

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import SongGeneratorStrategy
from .mock_strategy import MockSongGeneratorStrategy
from .suno_strategy import SunoSongGeneratorStrategy


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Each value is a zero-argument callable that produces a ready-to-use
# strategy instance. Using a factory callable (rather than the class
# itself) lets us pull configuration out of Django settings *lazily* —
# i.e. only when the strategy is actually requested — which means tests
# and management commands that never touch Suno do not need the
# SUNO_API_KEY to be set.

def _build_mock() -> SongGeneratorStrategy:
    """Factory for the offline mock strategy (takes no configuration)."""
    return MockSongGeneratorStrategy()


def _build_suno() -> SongGeneratorStrategy:
    """
    Factory for the Suno-backed strategy.

    Reads credentials and tuning knobs from Django settings so the
    rest of the codebase never has to import ``os.environ``.
    """
    api_key = getattr(settings, "SUNO_API_KEY", "") or ""
    base_url = getattr(settings, "SUNO_API_BASE_URL", None)
    timeout = int(getattr(settings, "SUNO_API_TIMEOUT", 30))
    model = getattr(settings, "SUNO_API_MODEL", "V4")
    callback_url = getattr(settings, "SUNO_CALLBACK_URL", None)
    return SunoSongGeneratorStrategy(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        model=model,
        callback_url=callback_url,
    )


#: Public registry. Map a short, lowercase name to a factory callable.
#: Keys in this dict are the only valid values for the
#: ``GENERATOR_STRATEGY`` environment variable.
STRATEGY_REGISTRY: Dict[str, Callable[[], SongGeneratorStrategy]] = {
    "mock": _build_mock,
    "suno": _build_suno,
}


# ---------------------------------------------------------------------------
# Public selector
# ---------------------------------------------------------------------------

def get_generator_strategy(name: str | None = None) -> SongGeneratorStrategy:
    """
    Return the strategy matching ``name`` (or the configured default).

    Parameters
    ----------
    name:
        Optional override. When ``None`` (the common case) the value
        of ``settings.GENERATOR_STRATEGY`` is used, which itself
        defaults to ``"mock"`` when unset — so a developer who simply
        clones the repo and runs the server gets a working, offline
        flow with zero configuration.

    Raises
    ------
    ImproperlyConfigured
        If ``name`` does not appear in :data:`STRATEGY_REGISTRY`. The
        error message lists the valid choices so the fix is obvious.
    """
    chosen = (name or getattr(settings, "GENERATOR_STRATEGY", "mock") or "mock").strip().lower()
    factory = STRATEGY_REGISTRY.get(chosen)
    if factory is None:
        valid = ", ".join(sorted(STRATEGY_REGISTRY)) or "(none registered)"
        raise ImproperlyConfigured(
            f"Unknown GENERATOR_STRATEGY={chosen!r}. "
            f"Valid options are: {valid}."
        )
    return factory()


__all__ = ["STRATEGY_REGISTRY", "get_generator_strategy"]
