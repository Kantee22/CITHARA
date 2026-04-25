"""
CITHARA Domain Layer - Song Entity
"""

import uuid
from django.core.exceptions import ValidationError
from django.db import models
from .enums import Genre, GenerationStatus
from .library import Library


# BR-04: a Song's duration must not exceed 15 minutes.
MAX_DURATION_SECONDS = 15 * 60


def _parse_duration_seconds(duration):
    """
    Parse a duration string like "3:42", "03:42", "1:02:30" or a bare
    "245" into total seconds. Returns None for empty input. Raises
    ValidationError for malformed values so that callers can surface
    a clean BR-04 message.
    """
    if duration in (None, ""):
        return None
    s = duration.strip()
    if not s:
        return None
    parts = s.split(":")
    if not all(p.isdigit() for p in parts):
        raise ValidationError(
            {"duration": "Duration must be digits separated by ':' (e.g. '3:42' or '1:02:30')."}
        )
    nums = [int(p) for p in parts]
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        m, sec = nums
        return m * 60 + sec
    if len(nums) == 3:
        h, m, sec = nums
        return h * 3600 + m * 60 + sec
    raise ValidationError(
        {"duration": "Duration has too many ':' segments."}
    )


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
        return "%s (%s)" % (self.title, self.get_genre_display())

    # ------------------------------------------------------------------
    # Business-rule enforcement
    # ------------------------------------------------------------------
    def clean(self):
        """
        Enforces:
          - BR-04: duration (if set) must be <= 15 minutes.
          - BR-06: a Library may hold at most CAPACITY_LIMIT (1,000,000)
            songs. Only checked on creation, so updating an existing
            Song never fails this rule.
        """
        super().clean()

        # BR-04 - duration cap
        seconds = _parse_duration_seconds(self.duration)
        if seconds is not None and seconds > MAX_DURATION_SECONDS:
            raise ValidationError(
                {"duration": "BR-04: duration must not exceed 15 minutes (got %ss)." % seconds}
            )

        # BR-06 - library capacity (only on creation)
        if self._state.adding and self.library_id and self.library.is_at_capacity:
            raise ValidationError(
                {"library": "BR-06: library has reached the 1,000,000 song capacity limit."}
            )

    def save(self, *args, **kwargs):
        """Run clean() so BR-04 / BR-06 fire for ORM saves too."""
        self.full_clean()
        super().save(*args, **kwargs)
