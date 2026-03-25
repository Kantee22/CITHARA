"""
CITHARA Domain Layer - Song Entity
"""

import uuid
from django.db import models
from .enums import Genre, GenerationStatus
from .library import Library


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
        app_label = 'music'
        db_table = 'songs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at'], name='idx_song_created_at'),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_genre_display()})"
