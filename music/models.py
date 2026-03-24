"""
CITHARA Domain Layer - Django Models

Domain entities implemented from the CITHARA Domain Model (Exercise 2).
This module defines all domain entities, enumerations, relationships,
and business rule constraints for the AI Music Generator application.

Entities: User, Library, Song, SongRequest, GenerationJob, ShareLink
Enumerations: Genre, Voice, GenerationStatus, DownloadFormat
"""

import uuid
from django.db import models
from django.core.validators import MaxLengthValidator, MinValueValidator, MaxValueValidator


# =============================================================================
# Enumerations
# =============================================================================

class Genre(models.TextChoices):
    """
    Allowed music genres for song creation.
    Traced from: FR-10, FR-11, BR-03, US-10
    """
    ROCK = 'ROCK', 'Rock'
    POP = 'POP', 'Pop'
    HIP_HOP = 'HIP_HOP', 'Hip-Hop'
    JAZZ = 'JAZZ', 'Jazz'
    COUNTRY = 'COUNTRY', 'Country'


class Voice(models.TextChoices):
    """
    Voice options for song generation.
    Traced from: FR-07, TBD-01, US-07
    Assumption A1: Voice is an optional enum with MALE/FEMALE values.
    """
    MALE = 'MALE', 'Male'
    FEMALE = 'FEMALE', 'Female'


class GenerationStatus(models.TextChoices):
    """
    Status of a generation job or song.
    Traced from: FR-14, Features 4.3, US-13
    """
    QUEUED = 'QUEUED', 'Queued'
    PROCESSING = 'PROCESSING', 'Processing'
    SUCCESS = 'SUCCESS', 'Success'
    FAILED = 'FAILED', 'Failed'


class DownloadFormat(models.TextChoices):
    """
    Supported download formats for songs.
    Traced from: FR-24, Features 4.5, US-24
    """
    MP3 = 'MP3', 'MP3'
    M4A = 'M4A', 'M4A'


# =============================================================================
# Domain Entities
# =============================================================================

class User(models.Model):
    """
    Represents an authenticated person who uses the system.
    A User may act as a Creator (generating songs) or a Listener
    (accessing shared songs). Authentication is primarily via Google OAuth.

    Traced from: Features 4.1, FR-01 to FR-06, US-01 to US-06, UC-01, UC-02, BR-01
    """
    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=255)
    google_id = models.CharField(max_length=255, unique=True, blank=True, null=True,
                                 help_text="Google OAuth ID. Null if manual login only.")
    password = models.CharField(max_length=255, blank=True, null=True,
                                help_text="Optional: for manual login (Assumption A4, FR-06)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.display_name} ({self.email})"


class Library(models.Model):
    """
    A personal collection of saved songs belonging to exactly one User.
    Enforces ownership isolation (BR-05) and a capacity limit of 1,000,000 songs (BR-06).

    Relationship: User owns Library (1:1 Composition)
    Traced from: Features 4.4, FR-18 to FR-22, US-18 to US-21, UC-05 to UC-07, BR-05, BR-06
    """
    library_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='library',
        help_text="Each user has exactly one library (BR-05). Cascade delete (Composition)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    CAPACITY_LIMIT = 1_000_000  # BR-06: max songs per library

    class Meta:
        db_table = 'libraries'
        verbose_name_plural = 'libraries'

    def __str__(self):
        return f"Library of {self.user.display_name}"

    @property
    def song_count(self):
        """Returns the current number of songs in this library."""
        return self.songs.count()

    @property
    def is_at_capacity(self):
        """Check if the library has reached the 1,000,000 song limit (BR-06)."""
        return self.song_count >= self.CAPACITY_LIMIT


class Song(models.Model):
    """
    A generated audio output that has been saved to a user's Library.
    Contains the final audio file URL, metadata (title, genre, duration),
    and a generation status.

    Relationship: Library contains Song (1:0..* Composition)
    Traced from: Features 4.2/4.4/4.5, FR-07/15/19/21/23/24, US-07/14/18/21-24,
                 UC-03/05/08, BR-03/04/08
    """
    song_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name='songs',
        help_text="Song belongs to a Library. Cascade delete (Composition)."
    )
    title = models.CharField(max_length=255)
    genre = models.CharField(
        max_length=10,
        choices=Genre.choices,
        help_text="Exactly one genre from the allowed list (BR-03)"
    )
    audio_file_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Server/storage URL of the generated audio file"
    )
    duration = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Duration string (BR-04: must not exceed 15 minutes)"
    )
    status = models.CharField(
        max_length=15,
        choices=GenerationStatus.choices,
        default=GenerationStatus.QUEUED,
        help_text="Current generation/availability status"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'songs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at'], name='idx_song_created_at'),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_genre_display()})"


class SongRequest(models.Model):
    """
    Captures the user's intent for song creation including form inputs
    (title, genre, voice, occasion, mood) and the prompt text.
    A SongRequest can produce multiple Songs through the regeneration workflow.

    Assumption A5: SongRequest is separated from Song because a single request
    can lead to multiple generation attempts via Regenerate (FR-16).

    Relationship: User creates SongRequest (1:0..*)
    Traced from: Features 4.2/4.3, FR-07 to FR-12/16, US-07 to US-11/15,
                 UC-03/04, BR-02/03
    """
    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='song_requests',
        help_text="The user who created this song request"
    )
    title = models.CharField(max_length=255, help_text="Required: song title (FR-07)")
    genre = models.CharField(
        max_length=10,
        choices=Genre.choices,
        help_text="Exactly one genre from the allowed list (BR-03, FR-10)"
    )
    voice = models.CharField(
        max_length=10,
        choices=Voice.choices,
        blank=True,
        null=True,
        help_text="Optional voice selection (TBD-01, Assumption A1)"
    )
    occasion = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional occasion for the song"
    )
    mood = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Optional mood for the song"
    )
    prompt_text = models.TextField(
        validators=[MaxLengthValidator(1000)],
        help_text="Required: prompt text, max 1000 characters (BR-02, FR-09)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'song_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Request: {self.title} by {self.user.display_name}"


class GenerationJob(models.Model):
    """
    Tracks the lifecycle of a single AI generation attempt.
    Stores progress (0-100%), status (QUEUED/PROCESSING/SUCCESS/FAILED),
    error messages, and timestamps.

    Relationship: SongRequest processes GenerationJob (1:1..*)
    Relationship: GenerationJob produces Song (1:0..1) — dependency
    Traced from: Features 4.3, FR-12 to FR-17, US-12/13/15/16, UC-03/04
    """
    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    song_request = models.ForeignKey(
        SongRequest,
        on_delete=models.CASCADE,
        related_name='generation_jobs',
        help_text="The song request that initiated this job"
    )
    song = models.OneToOneField(
        Song,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generation_job',
        help_text="The produced song (0..1). Dependency: job produces song."
    )
    progress = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Generation progress percentage (0-100%)"
    )
    status = models.CharField(
        max_length=15,
        choices=GenerationStatus.choices,
        default=GenerationStatus.QUEUED,
        help_text="Current job status"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Error details if generation failed (FR-17)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when the job finished (success or failure)"
    )

    class Meta:
        db_table = 'generation_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Job {self.job_id} [{self.get_status_display()}] - {self.progress}%"


class ShareLink(models.Model):
    """
    A URL token that grants access to a Song for external Listeners.
    Contains an unguessable token, an active/inactive state for revocation,
    and an access counter.

    Assumption A2: Public access by default; isActive flag supports revocation (NFR-SEC-05).

    Relationship: Song shared via ShareLink (1:0..*)
    Relationship: User creates ShareLink (1:0..*) — dependency
    Traced from: Features 4.5, FR-25/26, US-25/26, UC-09/10, BR-07/08
    """
    share_link_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(
        max_length=255,
        unique=True,
        default=uuid.uuid4,
        help_text="Unguessable token for the share link (NFR-SEC-05)"
    )
    song = models.ForeignKey(
        Song,
        on_delete=models.CASCADE,
        related_name='share_links',
        help_text="The song being shared. Cascade delete revokes links (BR-08)."
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='share_links',
        help_text="The user who created this share link"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this link is active. Supports revocation (Assumption A2, NFR-SEC-05)."
    )
    access_count = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Number of times this link has been accessed"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'share_links'
        ordering = ['-created_at']

    def __str__(self):
        return f"ShareLink for '{self.song.title}' ({'Active' if self.is_active else 'Inactive'})"
