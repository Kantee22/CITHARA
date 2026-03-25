"""
CITHARA Domain Layer - ShareLink Entity
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator
from .song import Song
from .user import User


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
        app_label = 'music'
        db_table = 'share_links'
        ordering = ['-created_at']

    def __str__(self):
        return f"ShareLink for '{self.song.title}' ({'Active' if self.is_active else 'Inactive'})"
