"""
Migration 0003 — add ``SAVED`` to the ``GenerationStatus`` enum.

Introduced by Exercise 5 (Web UI). SRS FR-15 requires a preview step
before a song is committed to the user's Library. We model the
distinction with a new status value:

* ``SUCCESS`` — generation succeeded; the song exists only as a
                preview and is not yet on the Library page.
* ``SAVED``   — the user clicked "Save to Library"; the song is now
                visible in the Library view.

Only the ``choices`` metadata changes — the underlying column already
stores up to 15 chars and accepts arbitrary strings. This migration
therefore alters the field definition on ``Song`` (and ``GenerationJob``
for symmetry) so Django's form/model validation recognises the new
option.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0002_generation_job_provider_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="song",
            name="status",
            field=models.CharField(
                choices=[
                    ("QUEUED", "Queued"),
                    ("PROCESSING", "Processing"),
                    ("SUCCESS", "Success"),
                    ("SAVED", "Saved"),
                    ("FAILED", "Failed"),
                ],
                default="QUEUED",
                help_text="Current generation/availability status",
                max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name="generationjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("QUEUED", "Queued"),
                    ("PROCESSING", "Processing"),
                    ("SUCCESS", "Success"),
                    ("SAVED", "Saved"),
                    ("FAILED", "Failed"),
                ],
                default="QUEUED",
                help_text="Current job status",
                max_length=15,
            ),
        ),
    ]
