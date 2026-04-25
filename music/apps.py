from django.apps import AppConfig


class MusicConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'music'

    def ready(self):
        """
        Import the ``music.signals`` module so the receivers register
        at startup. The import itself is the whole side-effect —
        Django's signal framework wires the ``@receiver`` decorators
        into the global dispatcher as soon as the module loads.
        """
        # Imported for side effects; ``noqa`` silences the unused-import
        # warning that linters would otherwise flag.
        from . import signals  # noqa: F401
