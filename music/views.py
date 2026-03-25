"""
CITHARA Domain Layer - Basic Views

Provides simple API-style views for CRUD operations on core domain entities.
This satisfies Exercise 3 Task 4: Demonstrate CRUD via simple views / API endpoints.
"""

import json
import uuid
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404

from .models import (
    User, Library, Song, SongRequest, GenerationJob, ShareLink,
    Genre, Voice, GenerationStatus,
)


# =============================================================================
# Helper
# =============================================================================

def _parse_json_body(request):
    """Parse JSON body from request, return dict or empty dict."""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return {}


# =============================================================================
# User Views
# =============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_list(request):
    """
    GET  /api/users/          → List all users
    POST /api/users/          → Create a new user
    """
    if request.method == "GET":
        users = User.objects.all().values(
            'user_id', 'email', 'display_name', 'google_id', 'created_at'
        )
        return JsonResponse(list(users), safe=False)

    # POST - Create
    data = _parse_json_body(request)
    if not data.get('email') or not data.get('display_name'):
        return JsonResponse({'error': 'email and display_name are required'}, status=400)

    user = User.objects.create(
        email=data['email'],
        display_name=data['display_name'],
        google_id=data.get('google_id'),
        password=data.get('password'),
    )
    return JsonResponse({
        'user_id': str(user.user_id),
        'email': user.email,
        'display_name': user.display_name,
        'message': 'User created successfully',
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def user_detail(request, user_id):
    """
    GET    /api/users/<user_id>/   → Read a single user
    PUT    /api/users/<user_id>/   → Update a user
    DELETE /api/users/<user_id>/   → Delete a user
    """
    user = get_object_or_404(User, user_id=user_id)

    if request.method == "GET":
        return JsonResponse({
            'user_id': str(user.user_id),
            'email': user.email,
            'display_name': user.display_name,
            'google_id': user.google_id,
            'created_at': user.created_at.isoformat(),
        })

    if request.method == "PUT":
        data = _parse_json_body(request)
        if 'display_name' in data:
            user.display_name = data['display_name']
        if 'email' in data:
            user.email = data['email']
        if 'google_id' in data:
            user.google_id = data['google_id']
        user.save()
        return JsonResponse({
            'user_id': str(user.user_id),
            'display_name': user.display_name,
            'email': user.email,
            'message': 'User updated successfully',
        })

    # DELETE
    user.delete()
    return JsonResponse({'message': 'User deleted successfully'})


# =============================================================================
# Library Views
# =============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def library_list(request):
    """
    GET  /api/libraries/       → List all libraries
    POST /api/libraries/       → Create a library for a user
    """
    if request.method == "GET":
        libraries = []
        for lib in Library.objects.select_related('user').all():
            libraries.append({
                'library_id': str(lib.library_id),
                'user': lib.user.display_name,
                'song_count': lib.song_count,
                'is_at_capacity': lib.is_at_capacity,
                'created_at': lib.created_at.isoformat(),
            })
        return JsonResponse(libraries, safe=False)

    # POST
    data = _parse_json_body(request)
    if not data.get('user_id'):
        return JsonResponse({'error': 'user_id is required'}, status=400)
    user = get_object_or_404(User, user_id=data['user_id'])
    library = Library.objects.create(user=user)
    return JsonResponse({
        'library_id': str(library.library_id),
        'user': user.display_name,
        'message': 'Library created successfully',
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def library_detail(request, library_id):
    """
    GET    /api/libraries/<library_id>/   → Read a library with its songs
    DELETE /api/libraries/<library_id>/   → Delete a library
    """
    library = get_object_or_404(Library, library_id=library_id)

    if request.method == "GET":
        songs = list(library.songs.values(
            'song_id', 'title', 'genre', 'status', 'duration', 'created_at'
        ))
        return JsonResponse({
            'library_id': str(library.library_id),
            'user': library.user.display_name,
            'song_count': library.song_count,
            'is_at_capacity': library.is_at_capacity,
            'songs': songs,
            'created_at': library.created_at.isoformat(),
        })

    # DELETE
    library.delete()
    return JsonResponse({'message': 'Library deleted successfully'})


# =============================================================================
# Song Views
# =============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def song_list(request):
    """
    GET  /api/songs/           → List all songs (with optional genre filter)
    POST /api/songs/           → Create a new song
    """
    if request.method == "GET":
        songs = Song.objects.select_related('library__user').all()

        # Optional filter by genre
        genre = request.GET.get('genre')
        if genre:
            songs = songs.filter(genre=genre)

        # Optional filter by status
        status = request.GET.get('status')
        if status:
            songs = songs.filter(status=status)

        result = []
        for song in songs:
            result.append({
                'song_id': str(song.song_id),
                'title': song.title,
                'genre': song.genre,
                'status': song.status,
                'duration': song.duration,
                'audio_file_url': song.audio_file_url,
                'owner': song.library.user.display_name,
                'created_at': song.created_at.isoformat(),
            })
        return JsonResponse(result, safe=False)

    # POST
    data = _parse_json_body(request)
    required = ['library_id', 'title', 'genre']
    if not all(data.get(f) for f in required):
        return JsonResponse({'error': 'library_id, title, and genre are required'}, status=400)

    library = get_object_or_404(Library, library_id=data['library_id'])
    if library.is_at_capacity:
        return JsonResponse({'error': 'Library has reached capacity (BR-06)'}, status=400)

    song = Song.objects.create(
        library=library,
        title=data['title'],
        genre=data['genre'],
        audio_file_url=data.get('audio_file_url'),
        duration=data.get('duration'),
        status=data.get('status', GenerationStatus.QUEUED),
    )
    return JsonResponse({
        'song_id': str(song.song_id),
        'title': song.title,
        'message': 'Song created successfully',
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def song_detail(request, song_id):
    """
    GET    /api/songs/<song_id>/   → Read a single song
    PUT    /api/songs/<song_id>/   → Update a song
    DELETE /api/songs/<song_id>/   → Delete a song
    """
    song = get_object_or_404(Song, song_id=song_id)

    if request.method == "GET":
        return JsonResponse({
            'song_id': str(song.song_id),
            'title': song.title,
            'genre': song.genre,
            'status': song.status,
            'duration': song.duration,
            'audio_file_url': song.audio_file_url,
            'owner': song.library.user.display_name,
            'created_at': song.created_at.isoformat(),
        })

    if request.method == "PUT":
        data = _parse_json_body(request)
        if 'title' in data:
            song.title = data['title']
        if 'genre' in data:
            song.genre = data['genre']
        if 'status' in data:
            song.status = data['status']
        if 'duration' in data:
            song.duration = data['duration']
        if 'audio_file_url' in data:
            song.audio_file_url = data['audio_file_url']
        song.save()
        return JsonResponse({
            'song_id': str(song.song_id),
            'title': song.title,
            'message': 'Song updated successfully',
        })

    # DELETE (BR-08: cascade deletes share links)
    song.delete()
    return JsonResponse({'message': 'Song deleted successfully (share links cascade deleted)'})


# =============================================================================
# SongRequest Views
# =============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def song_request_list(request):
    """
    GET  /api/song-requests/   → List all song requests
    POST /api/song-requests/   → Create a new song request
    """
    if request.method == "GET":
        requests = SongRequest.objects.select_related('user').all()
        result = []
        for req in requests:
            result.append({
                'request_id': str(req.request_id),
                'user': req.user.display_name,
                'title': req.title,
                'genre': req.genre,
                'voice': req.voice,
                'occasion': req.occasion,
                'mood': req.mood,
                'prompt_text': req.prompt_text,
                'created_at': req.created_at.isoformat(),
            })
        return JsonResponse(result, safe=False)

    # POST
    data = _parse_json_body(request)
    required = ['user_id', 'title', 'genre', 'prompt_text']
    if not all(data.get(f) for f in required):
        return JsonResponse(
            {'error': 'user_id, title, genre, and prompt_text are required'}, status=400
        )
    if len(data['prompt_text']) > 1000:
        return JsonResponse({'error': 'prompt_text must not exceed 1000 characters (BR-02)'}, status=400)

    user = get_object_or_404(User, user_id=data['user_id'])
    song_req = SongRequest.objects.create(
        user=user,
        title=data['title'],
        genre=data['genre'],
        voice=data.get('voice'),
        occasion=data.get('occasion'),
        mood=data.get('mood'),
        prompt_text=data['prompt_text'],
    )
    return JsonResponse({
        'request_id': str(song_req.request_id),
        'title': song_req.title,
        'message': 'Song request created successfully',
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def song_request_detail(request, request_id):
    """
    GET    /api/song-requests/<request_id>/   → Read a song request with its jobs
    DELETE /api/song-requests/<request_id>/   → Delete a song request
    """
    song_req = get_object_or_404(SongRequest, request_id=request_id)

    if request.method == "GET":
        jobs = list(song_req.generation_jobs.values(
            'job_id', 'status', 'progress', 'error_message', 'created_at', 'completed_at'
        ))
        return JsonResponse({
            'request_id': str(song_req.request_id),
            'user': song_req.user.display_name,
            'title': song_req.title,
            'genre': song_req.genre,
            'voice': song_req.voice,
            'occasion': song_req.occasion,
            'mood': song_req.mood,
            'prompt_text': song_req.prompt_text,
            'generation_jobs': jobs,
            'created_at': song_req.created_at.isoformat(),
        })

    # DELETE
    song_req.delete()
    return JsonResponse({'message': 'Song request deleted successfully'})


# =============================================================================
# GenerationJob Views
# =============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def generation_job_list(request):
    """
    GET  /api/generation-jobs/  → List all generation jobs
    POST /api/generation-jobs/  → Create a new generation job
    """
    if request.method == "GET":
        jobs = GenerationJob.objects.select_related('song_request', 'song').all()
        result = []
        for job in jobs:
            result.append({
                'job_id': str(job.job_id),
                'request_title': job.song_request.title,
                'song_title': job.song.title if job.song else None,
                'status': job.status,
                'progress': job.progress,
                'error_message': job.error_message,
                'created_at': job.created_at.isoformat(),
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            })
        return JsonResponse(result, safe=False)

    # POST
    data = _parse_json_body(request)
    if not data.get('song_request_id'):
        return JsonResponse({'error': 'song_request_id is required'}, status=400)

    song_req = get_object_or_404(SongRequest, request_id=data['song_request_id'])
    song = None
    if data.get('song_id'):
        song = get_object_or_404(Song, song_id=data['song_id'])

    job = GenerationJob.objects.create(
        song_request=song_req,
        song=song,
        status=data.get('status', GenerationStatus.QUEUED),
        progress=data.get('progress', 0),
    )
    return JsonResponse({
        'job_id': str(job.job_id),
        'message': 'Generation job created successfully',
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def generation_job_detail(request, job_id):
    """
    GET    /api/generation-jobs/<job_id>/   → Read a generation job
    PUT    /api/generation-jobs/<job_id>/   → Update a generation job
    DELETE /api/generation-jobs/<job_id>/   → Delete a generation job
    """
    job = get_object_or_404(GenerationJob, job_id=job_id)

    if request.method == "GET":
        return JsonResponse({
            'job_id': str(job.job_id),
            'request_title': job.song_request.title,
            'song_title': job.song.title if job.song else None,
            'status': job.status,
            'progress': job.progress,
            'error_message': job.error_message,
            'created_at': job.created_at.isoformat(),
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        })

    if request.method == "PUT":
        data = _parse_json_body(request)
        if 'status' in data:
            job.status = data['status']
        if 'progress' in data:
            job.progress = data['progress']
        if 'error_message' in data:
            job.error_message = data['error_message']
        if data.get('status') in [GenerationStatus.SUCCESS, GenerationStatus.FAILED]:
            from django.utils import timezone
            job.completed_at = timezone.now()
        job.save()
        return JsonResponse({
            'job_id': str(job.job_id),
            'status': job.status,
            'progress': job.progress,
            'message': 'Generation job updated successfully',
        })

    # DELETE
    job.delete()
    return JsonResponse({'message': 'Generation job deleted successfully'})


# =============================================================================
# ShareLink Views
# =============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
def share_link_list(request):
    """
    GET  /api/share-links/     → List all share links
    POST /api/share-links/     → Create a new share link
    """
    if request.method == "GET":
        links = ShareLink.objects.select_related('song', 'created_by').all()
        result = []
        for link in links:
            result.append({
                'share_link_id': str(link.share_link_id),
                'token': str(link.token),
                'song_title': link.song.title,
                'created_by': link.created_by.display_name,
                'is_active': link.is_active,
                'access_count': link.access_count,
                'created_at': link.created_at.isoformat(),
            })
        return JsonResponse(result, safe=False)

    # POST
    data = _parse_json_body(request)
    if not data.get('song_id') or not data.get('created_by_id'):
        return JsonResponse({'error': 'song_id and created_by_id are required'}, status=400)

    song = get_object_or_404(Song, song_id=data['song_id'])
    user = get_object_or_404(User, user_id=data['created_by_id'])

    link = ShareLink.objects.create(song=song, created_by=user)
    return JsonResponse({
        'share_link_id': str(link.share_link_id),
        'token': str(link.token),
        'message': 'Share link created successfully',
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
def share_link_detail(request, share_link_id):
    """
    GET    /api/share-links/<id>/   → Read a share link
    PUT    /api/share-links/<id>/   → Update a share link (toggle active, increment access)
    DELETE /api/share-links/<id>/   → Delete a share link
    """
    link = get_object_or_404(ShareLink, share_link_id=share_link_id)

    if request.method == "GET":
        return JsonResponse({
            'share_link_id': str(link.share_link_id),
            'token': str(link.token),
            'song_title': link.song.title,
            'created_by': link.created_by.display_name,
            'is_active': link.is_active,
            'access_count': link.access_count,
            'created_at': link.created_at.isoformat(),
        })

    if request.method == "PUT":
        data = _parse_json_body(request)
        if 'is_active' in data:
            link.is_active = data['is_active']
        if 'access_count' in data:
            link.access_count = data['access_count']
        if data.get('increment_access'):
            link.access_count += 1
        link.save()
        return JsonResponse({
            'share_link_id': str(link.share_link_id),
            'is_active': link.is_active,
            'access_count': link.access_count,
            'message': 'Share link updated successfully',
        })

    # DELETE
    link.delete()
    return JsonResponse({'message': 'Share link deleted successfully'})
