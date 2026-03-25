"""
CITHARA Domain Layer - User Entity
"""

import uuid
from django.db import models


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
        app_label = 'music'
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.display_name} ({self.email})"
