"""
Migration 0002 — add Strategy-Pattern bookkeeping fields to GenerationJob.

Introduced by Exercise 4. The two new columns are purely additive and
default to the empty string, so existing rows are untouched.

* ``provider``         — name of the strategy that produced the job
                         (e.g. "mock", "suno").
* ``provider_task_id`` — the external id returned by the strategy's
                         ``generate()`` call; used as the key when
                         polling ``get_status()``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("music", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="generationjob",
            name="provider",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Name of the generator strategy used (e.g. 'mock', 'suno').",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="generationjob",
            name="provider_task_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="External task id returned by the strategy (polling key).",
                max_length=128,
            ),
        ),
    ]
