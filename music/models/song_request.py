"""
CITHARA Domain Layer - SongRequest Entity
"""

import uuid
from django.db import models
from django.core.validators import MaxLengthValidator
from .enums import Genre, Voice
from .user import User


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
        app_label = 'music'
        db_table = 'song_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Request: {self.title} by {self.user.display_name}"
