"""
CITHARA Generation Package — Strategy Pattern for Song Generation
==================================================================

Exercise 4: Apply Strategy Pattern for Song Generation.

This package decouples *domain logic* (SongRequest, GenerationJob, Song)
from *generation implementation* (mock vs. Suno API) so that the active
generation behavior can be swapped via a single configuration switch
(``settings.GENERATOR_STRATEGY``).

Public surface
--------------
* :class:`SongGeneratorStrategy` — abstract base defining the contract.
* :class:`GenerationRequest`     — typed input to ``generate()``.
* :class:`GenerationResult`      — typed output from ``generate()`` /
  ``get_status()``.
* :func:`get_generator_strategy` — centralized factory that returns the
  currently configured strategy instance (mock or suno).
"""

from .base import (
    SongGeneratorStrategy,
    GenerationRequest,
    GenerationResult,
    StrategyStatus,
)
from .factory import get_generator_strategy, STRATEGY_REGISTRY

__all__ = [
    'SongGeneratorStrategy',
    'GenerationRequest',
    'GenerationResult',
    'StrategyStatus',
    'get_generator_strategy',
    'STRATEGY_REGISTRY',
]
