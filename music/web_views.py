"""
Web UI views — Exercise 5.

Maps the five pages required by SRS §3.1 onto Django views:

  /            → Landing  (marketing / entry page, FR-01)
  /login/      → Login    (proxied to allauth; shows Google button)
  /create/     → Create Song (FR-07 – FR-17)
  /library/    → Library  (FR-18 – FR-24)
  /share/<tok> → Share    (FR-25, FR-26 — public, no auth required)

All authenticated pages require the session to be tied to a Django
``auth.User``. The corresponding ``music.User`` (domain entity from
Exercise 2/3) is resolved through :func:`music.signals.get_music_user_for`
— kept in sync via post-login signals — so the existing ORM models
don't need to change.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

try:
    import requests  # noqa: F401  — also imported elsewhere; keeps this view self-contained.
except ImportError:  # pragma: no cover - requests is in requirements.txt
    requests = None  # type: ignore[assignment]

from . import services
from .models import (
    GenerationJob, GenerationStatus, Genre, ShareLink, Song, SongRequest, Voice,
)
from .signals import get_music_user_for

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page 1 — Landing
# ---------------------------------------------------------------------------

def landing(request):
    """Public entry page — shows product pitch and a login CTA."""
    return render(request, "pages/landing.html", {
        "genres": Genre.choices,
    })


# ---------------------------------------------------------------------------
# Page 3 — Create Song (login required)
# ---------------------------------------------------------------------------

@login_required
def create_song(request):
    """
    Page that lets a logged-in user fill in the song form and preview
    the generated track before saving.

    GET  → render form + most recent preview (if any)
    POST is handled by ``create_song_submit`` below (a JSON endpoint
    the page calls via fetch()).
    """
    music_user = get_music_user_for(request.user)
    if music_user is None:
        messages.error(request, "Could not resolve your profile. Please sign in again.")
        return redirect("account_logout")

    # Most recent preview (status == SUCCESS, not yet saved).
    preview = (
        Song.objects
        .filter(library__user=music_user, status=GenerationStatus.SUCCESS)
        .order_by("-created_at")
        .first()
    )

    return render(request, "pages/create_song.html", {
        "genres": Genre.choices,
        "voices": Voice.choices,
        "preview": preview,
    })


@csrf_protect
@login_required
@require_http_methods(["POST"])
def create_song_submit(request):
    """
    POST /create/submit/  — JSON endpoint used by the Create Song page.

    Body:
        {"title": "...", "genre": "POP", "voice": "MALE",
         "occasion": "...", "mood": "...", "prompt_text": "..."}

    Returns the serialized GenerationJob so the frontend can start
    polling ``/create/poll/<job_id>/`` for status.
    """
    music_user = get_music_user_for(request.user)
    if music_user is None:
        return JsonResponse({"error": "profile not found"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return HttpResponseBadRequest("invalid JSON")

    required = ("title", "genre", "prompt_text")
    missing = [f for f in required if not (data.get(f) or "").strip()]
    if missing:
        return JsonResponse(
            {"error": f"missing required fields: {', '.join(missing)}"}, status=400
        )
    if len(data["prompt_text"]) > 1000:
        return JsonResponse({"error": "prompt_text must not exceed 1000 characters (BR-02)"}, status=400)
    if data["genre"] not in Genre.values:
        return JsonResponse({"error": f"genre must be one of {Genre.values}"}, status=400)

    song_req = SongRequest.objects.create(
        user=music_user,
        title=data["title"].strip()[:255],
        genre=data["genre"],
        voice=(data.get("voice") or None),
        occasion=(data.get("occasion") or None),
        mood=(data.get("mood") or None),
        prompt_text=data["prompt_text"],
    )
    job = services.start_generation(song_req)
    return JsonResponse(_serialize_job(job), status=201)


@login_required
@require_http_methods(["GET"])
def create_song_poll(request, job_id):
    """GET /create/poll/<job_id>/  — refresh and return a job's state."""
    music_user = get_music_user_for(request.user)
    job = get_object_or_404(GenerationJob, job_id=job_id)
    if job.song_request.user_id != music_user.user_id:
        return HttpResponseForbidden("not your job")
    job = services.refresh_generation_job(job)
    return JsonResponse(_serialize_job(job))


@csrf_protect
@login_required
@require_http_methods(["POST"])
def create_song_save(request, song_id):
    """POST /create/save/<song_id>/  — promote preview → library (FR-15)."""
    music_user = get_music_user_for(request.user)
    song = get_object_or_404(Song, song_id=song_id)
    if song.library.user_id != music_user.user_id:
        return HttpResponseForbidden("not your song")
    services.save_song_to_library(song)
    return JsonResponse({"ok": True, "song_id": str(song.song_id), "status": song.status})


@csrf_protect
@login_required
@require_http_methods(["POST"])
def create_song_discard(request, song_id):
    """POST /create/discard/<song_id>/  — drop a preview the user rejected."""
    music_user = get_music_user_for(request.user)
    song = get_object_or_404(Song, song_id=song_id)
    if song.library.user_id != music_user.user_id:
        return HttpResponseForbidden("not your song")
    services.discard_preview_song(song)
    return JsonResponse({"ok": True})


@csrf_protect
@login_required
@require_http_methods(["POST"])
def create_song_regenerate(request, song_id):
    """
    POST /create/regenerate/<song_id>/  — SRS FR-16.

    "Regenerate using the same SongRequest" — without forcing the user
    to retype any form field. We look up the originating ``SongRequest``
    (via the linked ``GenerationJob``), drop the rejected preview Song,
    and kick off a brand-new ``GenerationJob`` against the same request.
    The new job's id is returned so the page can resume its polling
    loop seamlessly.
    """
    music_user = get_music_user_for(request.user)
    song = get_object_or_404(Song, song_id=song_id)
    if song.library.user_id != music_user.user_id:
        return HttpResponseForbidden("not your song")

    # The Song <- GenerationJob -> SongRequest chain. ``related_name``
    # on GenerationJob.song is "generation_job" (OneToOne), so we can
    # walk straight to the originating request. Django's reverse OneToOne
    # accessor raises ``RelatedObjectDoesNotExist`` when nothing's there
    # — catch and fall through to the explicit query as a safety net.
    job = None
    try:
        job = song.generation_job
    except GenerationJob.DoesNotExist:
        job = None
    if job is None or job.song_request is None:
        job = GenerationJob.objects.filter(song=song).order_by("-created_at").first()
    if job is None or job.song_request is None:
        return JsonResponse(
            {"error": "Cannot regenerate: original SongRequest is missing."},
            status=409,
        )

    song_request = job.song_request

    # Discard the rejected preview so only one preview ever exists per
    # user (matches the create_song view's "most recent preview" query).
    services.discard_preview_song(song)

    new_job = services.start_generation(song_request)
    return JsonResponse(_serialize_job(new_job), status=201)


# ---------------------------------------------------------------------------
# Page 4 — Library
# ---------------------------------------------------------------------------

@login_required
def library(request):
    """
    SRS FR-18/19/20/21: list the user's saved songs with filters.

    Query params:
      q      — substring match on title (FR-21)
      genre  — one of Genre.values
      sort   — "newest" (default), "oldest", "title"
    """
    music_user = get_music_user_for(request.user)
    if music_user is None:
        return redirect("account_logout")

    songs = Song.objects.filter(
        library__user=music_user,
        status=GenerationStatus.SAVED,
    )

    q = (request.GET.get("q") or "").strip()
    if q:
        songs = songs.filter(title__icontains=q)

    genre = (request.GET.get("genre") or "").strip().upper()
    if genre and genre in Genre.values:
        songs = songs.filter(genre=genre)

    sort = request.GET.get("sort") or "newest"
    if sort == "oldest":
        songs = songs.order_by("created_at")
    elif sort == "title":
        songs = songs.order_by("title")
    else:  # newest
        songs = songs.order_by("-created_at")

    return render(request, "pages/library.html", {
        "songs": songs,
        "genres": Genre.choices,
        "q": q,
        "active_genre": genre,
        "active_sort": sort,
    })


@csrf_protect
@login_required
@require_http_methods(["POST"])
def library_delete(request, song_id):
    """POST /library/<song_id>/delete/ — remove a saved song (BR-08 cascades share links)."""
    music_user = get_music_user_for(request.user)
    song = get_object_or_404(Song, song_id=song_id)
    if song.library.user_id != music_user.user_id:
        return HttpResponseForbidden("not your song")
    song.delete()
    messages.success(request, "Song deleted.")
    return redirect("library")


@csrf_protect
@login_required
@require_http_methods(["POST"])
def library_share(request, song_id):
    """POST /library/<song_id>/share/ — create a new ShareLink (FR-25)."""
    music_user = get_music_user_for(request.user)
    song = get_object_or_404(Song, song_id=song_id)
    if song.library.user_id != music_user.user_id:
        return HttpResponseForbidden("not your song")
    link = ShareLink.objects.create(song=song, created_by=music_user)
    share_url = request.build_absolute_uri(
        reverse("share_public", kwargs={"token": str(link.token)})
    )
    return JsonResponse({
        "ok": True,
        "token": str(link.token),
        "url": share_url,
        "song_title": song.title,
    })


# ---------------------------------------------------------------------------
# Page 5 — Share (public — no login)
# ---------------------------------------------------------------------------

def share_public(request, token):
    """
    GET /share/<token>/  — publicly accessible listen page.

    Resolves the ShareLink, bumps its access counter, and renders a
    slim page with an audio player. Inactive (revoked) links render
    a 410-style page.
    """
    link = get_object_or_404(ShareLink, token=str(token))
    if not link.is_active:
        return render(request, "pages/share_inactive.html", status=410)

    # FR-26: increment access counter on every GET.
    link.access_count += 1
    link.save(update_fields=["access_count"])

    return render(request, "pages/share.html", {
        "song": link.song,
        "owner": link.created_by.display_name,
        "access_count": link.access_count,
        # Re-exposed so the template can build a URL for ``share_download``
        # (which needs the token, not the Song id).
        "link_token": str(link.token),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_job(job: GenerationJob) -> dict:
    """JSON shape used by the create-song page's polling loop."""
    return {
        "job_id": str(job.job_id),
        "provider": job.provider,
        "provider_task_id": job.provider_task_id,
        "status": job.status,
        "progress": job.progress,
        "error_message": job.error_message,
        "song": {
            "song_id": str(job.song.song_id),
            "title": job.song.title,
            "genre": job.song.genre,
            "audio_file_url": job.song.audio_file_url,
            "duration": job.song.duration,
            "status": job.song.status,
        } if job.song else None,
    }


# ---------------------------------------------------------------------------
# Download — choose format (mp3 vs m4a)
# ---------------------------------------------------------------------------
# Suno's CDN serves an MP3 file. For users who want a more
# Apple-friendly container we transcode to AAC-in-MP4 (.m4a) on the
# fly using ffmpeg. The format choice is exposed as a ``?format=mp3``
# or ``?format=m4a`` query string on both the authenticated Library
# download and the public Share download.

_ALLOWED_DOWNLOAD_FORMATS = ("mp3", "m4a")
_FFMPEG_BIN = shutil.which("ffmpeg")  # Cached at import time.


def _slugify_title(title: str) -> str:
    """Filesystem-safe filename derived from the song title (no extension)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "song").strip())
    return cleaned.strip("._-") or "song"


def _stream_upstream_mp3(url: str):
    """Yield bytes from the upstream Suno MP3, in 64KB chunks."""
    if requests is None:  # pragma: no cover
        raise RuntimeError("requests library is not installed")
    upstream = requests.get(url, stream=True, timeout=60)
    upstream.raise_for_status()
    try:
        for chunk in upstream.iter_content(chunk_size=64 * 1024):
            if chunk:
                yield chunk
    finally:
        upstream.close()


def _stream_transcoded_m4a(url: str):
    """
    Stream a re-encoded AAC/MP4 (.m4a) by piping the MP3 through ffmpeg.

    Uses ``-movflags frag_keyframe+empty_moov`` so the MP4 container is
    fragmented and can be written to a non-seekable stdout pipe — without
    that flag ffmpeg fails with "muxer does not support non seekable
    output". Audio is re-encoded to AAC at 192 kbps which is the de-facto
    quality target for music downloads.
    """
    if _FFMPEG_BIN is None:
        raise RuntimeError(
            "ffmpeg is not installed on this server, so M4A download is "
            "unavailable. Pick MP3 instead, or install ffmpeg "
            "(https://ffmpeg.org/) and restart the server."
        )
    if requests is None:  # pragma: no cover
        raise RuntimeError("requests library is not installed")

    # Spawn ffmpeg reading from stdin, writing to stdout. We feed it
    # the upstream MP3 bytes from a background thread so this view
    # itself stays a simple iterator.
    proc = subprocess.Popen(
        [
            _FFMPEG_BIN,
            "-loglevel", "error",
            "-i", "pipe:0",
            "-vn",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "frag_keyframe+empty_moov",
            "-f", "mp4",
            "pipe:1",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    import threading

    def _feed():
        try:
            upstream = requests.get(url, stream=True, timeout=60)
            upstream.raise_for_status()
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    proc.stdin.write(chunk)
        except Exception:  # pragma: no cover - network-dependent
            logger.exception("Upstream MP3 fetch failed during M4A transcode")
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    feeder = threading.Thread(target=_feed, daemon=True)
    feeder.start()

    try:
        while True:
            chunk = proc.stdout.read(64 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        for closer in (proc.stdout, proc.stderr):
            try:
                if closer is not None:
                    closer.close()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
        feeder.join(timeout=2)


def _build_download_response(song: Song, fmt: str) -> HttpResponse:
    """Common download handler shared by Library and Share views."""
    fmt = (fmt or "mp3").strip().lower()
    if fmt not in _ALLOWED_DOWNLOAD_FORMATS:
        return JsonResponse(
            {"error": f"format must be one of: {', '.join(_ALLOWED_DOWNLOAD_FORMATS)}"},
            status=400,
        )
    if not song.audio_file_url:
        return JsonResponse({"error": "Audio is not yet available."}, status=409)

    filename = f"{_slugify_title(song.title)}.{fmt}"

    if fmt == "mp3":
        content_type = "audio/mpeg"
        try:
            stream = _stream_upstream_mp3(song.audio_file_url)
        except Exception as exc:  # pragma: no cover - network-dependent
            logger.exception("Upstream MP3 fetch failed")
            return JsonResponse({"error": str(exc)}, status=502)
    else:  # m4a
        content_type = "audio/mp4"
        if _FFMPEG_BIN is None:
            return JsonResponse(
                {
                    "error": (
                        "M4A download requires ffmpeg on the server. "
                        "Pick MP3 instead, or install ffmpeg and restart the server."
                    )
                },
                status=503,
            )
        try:
            stream = _stream_transcoded_m4a(song.audio_file_url)
        except Exception as exc:  # pragma: no cover - depends on ffmpeg
            logger.exception("M4A transcode failed")
            return JsonResponse({"error": str(exc)}, status=500)

    response = StreamingHttpResponse(stream, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    # Help proxies / browsers know not to cache an authenticated stream.
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_http_methods(["GET"])
def library_download(request, song_id):
    """GET /library/<song_id>/download/?format=mp3|m4a — owner-only."""
    music_user = get_music_user_for(request.user)
    song = get_object_or_404(Song, song_id=song_id)
    if song.library.user_id != music_user.user_id:
        return HttpResponseForbidden("not your song")
    return _build_download_response(song, request.GET.get("format", "mp3"))


@require_http_methods(["GET"])
def share_download(request, token):
    """
    GET /share/<token>/download/?format=mp3|m4a — public.

    Same access rules as :func:`share_public`: revoked links return 410
    so the download button can't be used after the owner toggles the
    share off.
    """
    link = get_object_or_404(ShareLink, token=str(token))
    if not link.is_active:
        return HttpResponse("This share link has been revoked.", status=410)
    return _build_download_response(link.song, request.GET.get("format", "mp3"))
