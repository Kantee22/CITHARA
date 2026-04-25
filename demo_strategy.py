"""
Exercise 4 — Strategy Pattern demonstration script.

Run with Django's management shell so models are available::

    python manage.py shell < demo_strategy.py

The script exercises the Strategy layer end-to-end:

1. Prints which strategy is currently active (set by
   ``GENERATOR_STRATEGY`` env var / ``.env``).
2. Creates a throw-away User + SongRequest.
3. Calls :func:`music.services.start_generation` — this goes through
   the factory, picks the configured strategy, and runs the full
   domain-to-strategy bridge.
4. If the job did not finish synchronously (i.e. real Suno in
   production), polls ``refresh_generation_job`` a few times.
5. Prints the resulting ``GenerationJob`` + ``Song`` record.
6. Finally flips the strategy in-memory to prove the *same* service
   call works against the alternate provider (Mock ↔ Suno), which is
   the whole point of the Strategy Pattern.

Nothing here talks to Suno unless ``GENERATOR_STRATEGY=suno`` AND
``SUNO_API_KEY`` are set — so the demo is safe to run offline.
"""

from __future__ import annotations

import os
import time
import uuid

import django

# Bootstrap Django when invoked via plain ``python demo_strategy.py``.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cithara_project.settings")
try:
    django.setup()
except Exception:
    pass

from django.conf import settings  # noqa: E402

from music import services  # noqa: E402
from music.generation import (  # noqa: E402
    STRATEGY_REGISTRY,
    GenerationRequest,
    StrategyStatus,
    get_generator_strategy,
)
from music.models import (  # noqa: E402
    GenerationStatus,
    Library,
    SongRequest,
    User,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(text: str) -> None:
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def _dump_job(job) -> None:
    print(f"  job_id            : {job.job_id}")
    print(f"  provider          : {job.provider!r}")
    print(f"  provider_task_id  : {job.provider_task_id!r}")
    print(f"  status            : {job.status}")
    print(f"  progress          : {job.progress}%")
    if job.error_message:
        print(f"  error_message     : {job.error_message}")
    if job.song_id:
        print(f"  -> song.title     : {job.song.title!r}")
        print(f"  -> song.audio_url : {job.song.audio_file_url}")
        print(f"  -> song.duration  : {job.song.duration}")


def _make_song_request(suffix: str) -> SongRequest:
    """Build a self-contained User + Library + SongRequest for the demo."""
    unique = uuid.uuid4().hex[:6]
    user = User.objects.create(
        email=f"demo-{suffix}-{unique}@cithara.local",
        display_name=f"Demo {suffix} {unique}",
    )
    Library.objects.create(user=user)
    return SongRequest.objects.create(
        user=user,
        title=f"Rainy Night in Bangkok ({suffix})",
        genre="JAZZ",
        voice="FEMALE",
        occasion="chill evening",
        mood="melancholic but warm",
        prompt_text=(
            "A slow jazz ballad about neon reflections on wet streets, "
            "gentle rain, a saxophone solo, and a hopeful finish."
        ),
    )


# ---------------------------------------------------------------------------
# Step 1 — strategy introspection
# ---------------------------------------------------------------------------

_banner("Exercise 4 — Strategy Pattern demo")
print(f"Active GENERATOR_STRATEGY setting : {settings.GENERATOR_STRATEGY!r}")
print(f"Registered strategies             : {sorted(STRATEGY_REGISTRY)}")
strategy = get_generator_strategy()
print(f"Instantiated strategy             : {strategy}")


# ---------------------------------------------------------------------------
# Step 2 — run the full service flow with the CONFIGURED strategy
# ---------------------------------------------------------------------------

_banner(f"Step 2 — start_generation() using '{strategy.name}' strategy")
req = _make_song_request(suffix=strategy.name)
job = services.start_generation(req)
_dump_job(job)

# Poll a few times if the provider hasn't finished synchronously
# (the mock completes immediately; Suno does not).
polls = 0
while job.status not in (GenerationStatus.SUCCESS, GenerationStatus.FAILED) and polls < 5:
    time.sleep(2)
    polls += 1
    print(f"  polling... (attempt {polls})")
    job = services.refresh_generation_job(job)

print("\nFinal job state:")
_dump_job(job)


# ---------------------------------------------------------------------------
# Step 3 — prove the pattern by switching strategy on the fly
# ---------------------------------------------------------------------------
# We bypass the env var by passing ``name=`` directly to the factory.
# This is exactly what makes the Strategy Pattern worth implementing:
# the service/view layer never changes, only the strategy instance.

other = "suno" if strategy.name == "mock" else "mock"
_banner(f"Step 3 — directly invoke the '{other}' strategy via the factory")

try:
    other_strategy = get_generator_strategy(other)
    print(f"Obtained strategy     : {other_strategy}")

    if other == "mock":
        # We can always call mock safely.
        result = other_strategy.generate(GenerationRequest(
            prompt_text=req.prompt_text,
            title=req.title,
            genre=req.genre,
            voice=req.voice,
            mood=req.mood,
            occasion=req.occasion,
        ))
        print(f"mock generate() -> status={result.status}, "
              f"audio={result.audio_url}, task_id={result.task_id}")
    else:
        # Calling Suno requires a real API key. Skip the network call
        # if the key is unset so the demo stays runnable offline.
        if not settings.SUNO_API_KEY:
            print("SUNO_API_KEY is not set — skipping live Suno call.")
            print("(Set SUNO_API_KEY in .env and rerun to exercise the real API.)")
        else:
            result = other_strategy.generate(GenerationRequest(
                prompt_text=req.prompt_text,
                title=req.title,
                genre=req.genre,
                voice=req.voice,
                mood=req.mood,
                occasion=req.occasion,
            ))
            print(f"suno generate() -> status={result.status}, "
                  f"task_id={result.task_id}")
except Exception as exc:
    print(f"Skipped: {type(exc).__name__}: {exc}")


_banner("Demo complete — the service layer never saw which provider ran.")
