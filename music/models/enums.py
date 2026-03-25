"""
CITHARA Domain Layer - Enumerations

Defines all enumerations used across the domain model.
"""

from django.db import models


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
