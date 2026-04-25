"""
Service Layer — domain ↔ strategy bridge.

This is the *only* module that knows how to translate between Django
ORM objects (``SongRequest`` / ``GenerationJob`` / ``Song``) and the
provider-agnostic Strategy contracts (``GenerationRequest`` /
``GenerationResult``). Keeping the translation in one place honors the
Single Responsibility Principle and keeps the views trivial.

Typical flow (Exercise 4 §4.3)::

    song_req = SongRequest.objects.get(pk=...)
    job = start_generation(song_req)            # picks the configured strategy
    ...
    job = refresh_generation_job(job)           # polls the same strategy

The service always uses :func:`music.generation.get_generator_strategy`
to obtain the strategy instance — application code never instantiates
``MockSongGeneratorStrategy`` / ``SunoSongGeneratorStrategy`` directly.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .generation import (
    GenerationRequest,
    GenerationResult,
    StrategyStatus,
    get_generator_strategy,
)
from .models import GenerationJob, GenerationStatus, Library, Song, SongRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status mapping: strategy → domain
# ---------------------------------------------------------------------------
# The strategies speak a provider-neutral vocabulary
# (:class:`StrategyStatus`); the domain model uses
# :class:`GenerationStatus`. We translate here so neither side depends
# on the other's enum.
_STATUS_TO_DOMAIN = {
    StrategyStatus.PENDING:    GenerationStatus.QUEUED,
    StrategyStatus.PROCESSING: GenerationStatus.PROCESSING,
    StrategyStatus.SUCCESS:    GenerationStatus.SUCCESS,
    StrategyStatus.FAILED:     GenerationStatus.FAILED,
}


def _to_domain_status(s: StrategyStatus) -> str:
    return _STATUS_TO_DOMAIN.get(s, GenerationStatus.QUEUED)


def _build_generation_request(song_request: SongRequest) -> GenerationRequest:
    """Copy the relevant form fields from the ORM into a plain dataclass."""
    return GenerationRequest(
        prompt_text=song_request.prompt_text,
        title=song_request.title,
        genre=song_request.genre or "",
        voice=song_request.voice,
        occasion=song_request.occasion,
        mood=song_request.mood,
        extra={},
    )


# ---------------------------------------------------------------------------
# Public service entry points
# ---------------------------------------------------------------------------

@transaction.atomic
def start_generation(song_request: SongRequest) -> GenerationJob:
    """
    Kick off a new generation for ``song_request``.

    Creates a fresh :class:`GenerationJob`, asks the currently
    configured strategy to ``generate()``, and persists the strategy's
    ``task_id`` + initial status on the job. If the strategy completes
    synchronously (e.g. the mock), the result is applied immediately so
    the returned job is already terminal.

    Returns the saved ``GenerationJob``.
    """
    strategy = get_generator_strategy()
    job = GenerationJob.objects.create(
        song_request=song_request,
        status=GenerationStatus.QUEUED,
        progress=0,
        provider=strategy.name,
    )

    try:
        result = strategy.generate(_build_generation_request(song_request))
    except Exception as exc:  # pragma: no cover - depends on provider
        logger.exception("Strategy %s failed during generate()", strategy.name)
        job.status = GenerationStatus.FAILED
        job.error_message = f"{type(exc).__name__}: {exc}"
        job.completed_at = timezone.now()
        job.save()
        return job

    _apply_result(job, result, song_request)
    return job


@transaction.atomic
def refresh_generation_job(job: GenerationJob) -> GenerationJob:
    """
    Poll the provider for an update and persist any changes on ``job``.

    Terminal jobs (SUCCESS / FAILED) short-circuit so callers can poll
    safely without duplicating work.
    """
    if job.status in (GenerationStatus.SUCCESS, GenerationStatus.FAILED):
        return job
    if not job.provider_task_id:
        # Nothing to poll — the initial submit never produced a task id.
        return job

    # Use the provider recorded on the job (falling back to the current
    # default) so a Suno job keeps polling Suno even if GENERATOR_STRATEGY
    # was flipped to "mock" after submission.
    strategy = get_generator_strategy(job.provider or None)

    try:
        result = strategy.get_status(job.provider_task_id)
    except Exception as exc:  # pragma: no cover - depends on provider
        logger.exception("Strategy %s failed during get_status()", strategy.name)
        job.status = GenerationStatus.FAILED
        job.error_message = f"{type(exc).__name__}: {exc}"
        job.completed_at = timezone.now()
        job.save()
        return job

    _apply_result(job, result, job.song_request)
    return job


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _apply_result(
    job: GenerationJob,
    result: GenerationResult,
    song_request: SongRequest,
) -> None:
    """
    Merge a fresh :class:`GenerationResult` onto the persistent job.

    On SUCCESS we additionally create (or update) the ``Song`` record
    and link it to the job so the generated audio is reachable from the
    user's library (FR-15 / US-14).
    """
    job.provider = result.strategy_name or job.provider
    if result.task_id:
        job.provider_task_id = result.task_id

    job.status = _to_domain_status(result.status)
    job.progress = max(0, min(100, int(result.progress or 0)))
    job.error_message = result.error_message

    if result.is_terminal:
        job.completed_at = timezone.now()

    if result.status == StrategyStatus.SUCCESS:
        job.song = _materialize_song(song_request, result, existing=job.song)

    job.save()


def _materialize_song(
    song_request: SongRequest,
    result: GenerationResult,
    existing: Optional[Song],
) -> Song:
    """
    Create the domain ``Song`` row from a successful generation.

    If the job already had a linked song (e.g. we're reapplying a
    poll), we update it in place rather than creating a duplicate.
    """
    # Users are supposed to own exactly one Library (BR-05), but the
    # demo creates users ad-hoc — fall back to get_or_create so the
    # service stays robust in any fixture ordering.
    library, _ = Library.objects.get_or_create(user=song_request.user)
    if existing is not None:
        existing.audio_file_url = result.audio_url
        existing.duration = result.duration
        existing.status = GenerationStatus.SUCCESS
        existing.save()
        return existing

    return Song.objects.create(
        library=library,
        title=song_request.title or "Untitled",
        genre=song_request.genre,
        audio_file_url=result.audio_url,
        duration=result.duration,
        status=GenerationStatus.SUCCESS,
    )


# ---------------------------------------------------------------------------
# Preview-before-save helpers (SRS FR-15 / FR-16 / FR-19)
# ---------------------------------------------------------------------------
# The SRS requires the user to see a *preview* before committing the
# song to their library. Our Strategy layer already persists a ``Song``
# on SUCCESS (so the audio URL is reachable), but whether that Song
# counts as "saved to the library" is a UI-level decision. We therefore
# track an explicit ``is_saved`` flag via the ``status`` field:
#
#   status == SUCCESS  → generation succeeded, awaiting user decision
#                         (displayed in the preview panel only).
#   status == SAVED    → user clicked "Save to Library" — now visible
#                         on the Library page (FR-19).
#
# ``GenerationStatus.SAVED`` is added to the enum. The Library page
# view filters on ``status=SAVED`` so ephemeral previews never leak in.

def save_song_to_library(song: Song) -> Song:
    """Promote a preview song to a permanent Library entry (FR-15)."""
    song.status = GenerationStatus.SAVED
    song.save(update_fields=["status"])
    return song


def discard_preview_song(song: Song) -> None:
    """Delete a preview song that the user chose not to keep (FR-16)."""
    song.delete()
