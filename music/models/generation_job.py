"""
CITHARA Domain Layer - GenerationJob Entity
"""

import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from .enums import GenerationStatus
from .song_request import SongRequest
from .song import Song


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
    # --- Exercise 4: Strategy Pattern bookkeeping ---------------------
    # ``provider`` records which concrete strategy produced the job so
    # we know how to poll it later even if the default GENERATOR_STRATEGY
    # has been flipped since submission.
    # ``provider_task_id`` stores the external id returned by the
    # strategy's ``generate()`` call (Suno ``taskId`` / mock hash id).
    provider = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Name of the generator strategy used (e.g. 'mock', 'suno')."
    )
    provider_task_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="External task id returned by the strategy (polling key)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when the job finished (success or failure)"
    )

    class Meta:
        app_label = 'music'
        db_table = 'generation_jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Job {self.job_id} [{self.get_status_display()}] - {self.progress}%"
