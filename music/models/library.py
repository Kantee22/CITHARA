"""
CITHARA Domain Layer - Library Entity
"""

import uuid
from django.db import models
from .user import User


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
        app_label = 'music'
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
