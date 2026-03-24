"""
CITHARA - CRUD Operations Demo Script

This script demonstrates Create, Read, Update, and Delete operations
for all core domain entities using Django ORM.

Usage:
    python manage.py shell < demo_crud.py

Or run within Django shell:
    exec(open('demo_crud.py').read())
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cithara_project.settings')
django.setup()

from django.utils import timezone
from music.models import (
    User, Library, Song, SongRequest, GenerationJob, ShareLink,
    Genre, Voice, GenerationStatus
)

SEPARATOR = "=" * 60


def print_section(title):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


# =========================================================================
# 1. CREATE Operations
# =========================================================================
print_section("1. CREATE Operations")

# --- Create User ---
user1 = User.objects.create(
    email="kantee@example.com",
    display_name="Kantee Laibuddee",
    google_id="google_oauth_123456"
)
print(f"[CREATE] User: {user1}")

user2 = User.objects.create(
    email="listener@example.com",
    display_name="Music Listener",
    google_id="google_oauth_789012"
)
print(f"[CREATE] User: {user2}")

# --- Create Library (1:1 with User, BR-05) ---
library1 = Library.objects.create(user=user1)
print(f"[CREATE] Library: {library1}")

library2 = Library.objects.create(user=user2)
print(f"[CREATE] Library: {library2}")

# --- Create Songs ---
song1 = Song.objects.create(
    library=library1,
    title="Midnight Jazz Vibes",
    genre=Genre.JAZZ,
    audio_file_url="https://storage.cithara.com/songs/midnight-jazz.mp3",
    duration="3:45",
    status=GenerationStatus.SUCCESS
)
print(f"[CREATE] Song: {song1}")

song2 = Song.objects.create(
    library=library1,
    title="Rock Anthem",
    genre=Genre.ROCK,
    audio_file_url="https://storage.cithara.com/songs/rock-anthem.mp3",
    duration="4:20",
    status=GenerationStatus.SUCCESS
)
print(f"[CREATE] Song: {song2}")

song3 = Song.objects.create(
    library=library1,
    title="Hip Hop Beat",
    genre=Genre.HIP_HOP,
    status=GenerationStatus.PROCESSING
)
print(f"[CREATE] Song: {song3}")

# --- Create SongRequest ---
request1 = SongRequest.objects.create(
    user=user1,
    title="Midnight Jazz Vibes",
    genre=Genre.JAZZ,
    voice=Voice.MALE,
    occasion="Late night relaxation",
    mood="Calm and smooth",
    prompt_text="Create a smooth jazz instrumental with saxophone and piano, "
                "perfect for a late night relaxation session. Include soft drums."
)
print(f"[CREATE] SongRequest: {request1}")

request2 = SongRequest.objects.create(
    user=user1,
    title="Rock Anthem",
    genre=Genre.ROCK,
    voice=Voice.MALE,
    mood="Energetic",
    prompt_text="Create an energetic rock anthem with electric guitar riffs "
                "and powerful drums. Make it feel like a stadium concert."
)
print(f"[CREATE] SongRequest: {request2}")

# --- Create GenerationJobs ---
job1 = GenerationJob.objects.create(
    song_request=request1,
    song=song1,
    progress=100,
    status=GenerationStatus.SUCCESS,
    completed_at=timezone.now()
)
print(f"[CREATE] GenerationJob: {job1}")

job2 = GenerationJob.objects.create(
    song_request=request2,
    song=song2,
    progress=100,
    status=GenerationStatus.SUCCESS,
    completed_at=timezone.now()
)
print(f"[CREATE] GenerationJob: {job2}")

# Job for regeneration (same request, new job)
job3 = GenerationJob.objects.create(
    song_request=request1,
    progress=45,
    status=GenerationStatus.PROCESSING
)
print(f"[CREATE] GenerationJob (regeneration): {job3}")

# --- Create ShareLinks ---
share1 = ShareLink.objects.create(
    song=song1,
    created_by=user1,
    is_active=True,
    access_count=0
)
print(f"[CREATE] ShareLink: {share1}")


# =========================================================================
# 2. READ Operations
# =========================================================================
print_section("2. READ Operations")

# --- Read all users ---
print("\n--- All Users ---")
for u in User.objects.all():
    print(f"  {u.display_name} | {u.email} | Created: {u.created_at}")

# --- Read user's library with songs ---
print(f"\n--- {user1.display_name}'s Library ---")
lib = user1.library
print(f"  Library ID: {lib.library_id}")
print(f"  Song Count: {lib.song_count}")
print(f"  At Capacity: {lib.is_at_capacity}")
for s in lib.songs.all():
    print(f"    - {s.title} | {s.get_genre_display()} | {s.get_status_display()} | {s.duration or 'N/A'}")

# --- Read song requests with related jobs ---
print(f"\n--- Song Requests by {user1.display_name} ---")
for req in user1.song_requests.all():
    jobs = req.generation_jobs.all()
    print(f"  Request: {req.title} | Genre: {req.get_genre_display()} | Jobs: {jobs.count()}")
    print(f"    Prompt: {req.prompt_text[:80]}...")
    for job in jobs:
        print(f"    -> Job {job.status} | Progress: {job.progress}%")

# --- Read share links for a song ---
print(f"\n--- Share Links for '{song1.title}' ---")
for link in song1.share_links.all():
    print(f"  Token: {link.token} | Active: {link.is_active} | Accesses: {link.access_count}")

# --- Filter songs by genre ---
print("\n--- Jazz Songs ---")
jazz_songs = Song.objects.filter(genre=Genre.JAZZ)
for s in jazz_songs:
    print(f"  {s.title} by {s.library.user.display_name}")

# --- Filter jobs by status ---
print("\n--- Processing Jobs ---")
processing_jobs = GenerationJob.objects.filter(status=GenerationStatus.PROCESSING)
for job in processing_jobs:
    print(f"  Job {job.job_id} | Request: {job.song_request.title} | Progress: {job.progress}%")


# =========================================================================
# 3. UPDATE Operations
# =========================================================================
print_section("3. UPDATE Operations")

# --- Update song status ---
print(f"\nBefore: Song '{song3.title}' status = {song3.get_status_display()}")
song3.status = GenerationStatus.SUCCESS
song3.audio_file_url = "https://storage.cithara.com/songs/hiphop-beat.mp3"
song3.duration = "2:58"
song3.save()
print(f"After:  Song '{song3.title}' status = {song3.get_status_display()}, duration = {song3.duration}")

# --- Update generation job progress ---
print(f"\nBefore: Job progress = {job3.progress}%, status = {job3.get_status_display()}")
job3.progress = 100
job3.status = GenerationStatus.SUCCESS
job3.completed_at = timezone.now()
job3.save()
print(f"After:  Job progress = {job3.progress}%, status = {job3.get_status_display()}")

# --- Update user display name ---
print(f"\nBefore: User display name = '{user1.display_name}'")
user1.display_name = "Kantee L."
user1.save()
print(f"After:  User display name = '{user1.display_name}'")

# --- Deactivate share link (revocation) ---
print(f"\nBefore: ShareLink active = {share1.is_active}")
share1.is_active = False
share1.save()
print(f"After:  ShareLink active = {share1.is_active} (link revoked)")

# --- Increment access count ---
share1.is_active = True
share1.access_count += 1
share1.save()
print(f"ShareLink access count incremented to {share1.access_count}")


# =========================================================================
# 4. DELETE Operations
# =========================================================================
print_section("4. DELETE Operations")

# --- Delete a share link ---
share_id = share1.share_link_id
share1.delete()
print(f"[DELETE] ShareLink {share_id} deleted")
print(f"  Remaining share links for '{song1.title}': {song1.share_links.count()}")

# --- Delete a song (BR-08: cascade deletes share links) ---
song2_title = song2.title
# First create a share link for song2 to demonstrate cascade
share_for_song2 = ShareLink.objects.create(song=song2, created_by=user1)
print(f"\n[CREATE] ShareLink for '{song2_title}' (to demonstrate cascade)")
print(f"  Share links before delete: {song2.share_links.count()}")
song2.delete()
print(f"[DELETE] Song '{song2_title}' deleted (cascade removes share links, BR-08)")
print(f"  ShareLinks remaining in DB: {ShareLink.objects.count()}")

# --- Delete a user (cascade: User -> Library -> Songs) ---
user2_name = user2.display_name
user2_lib_songs = library2.songs.count()
user2.delete()
print(f"\n[DELETE] User '{user2_name}' deleted (cascade removes Library and Songs)")
print(f"  Total users: {User.objects.count()}")
print(f"  Total libraries: {Library.objects.count()}")


# =========================================================================
# Summary
# =========================================================================
print_section("Final Database State")
print(f"  Users:          {User.objects.count()}")
print(f"  Libraries:      {Library.objects.count()}")
print(f"  Songs:          {Song.objects.count()}")
print(f"  SongRequests:   {SongRequest.objects.count()}")
print(f"  GenerationJobs: {GenerationJob.objects.count()}")
print(f"  ShareLinks:     {ShareLink.objects.count()}")
print(f"\n{'=' * 60}")
print("  CRUD Demo Complete!")
print(f"{'=' * 60}\n")
