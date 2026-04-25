"""
Business-rule tests — automated coverage of the BR-XX constraints
declared in the SRS, plus a smoke test for the Strategy contract and
view authentication.

Run from the project root with::

    python manage.py test music

Each test maps to exactly one rule so a failure points straight at the
violated requirement.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.urls import reverse

from music.generation.base import (
    GenerationRequest,
    GenerationResult,
    StrategyStatus,
)
from music.generation.mock_strategy import MockSongGeneratorStrategy
from music.models import (
    GenerationStatus,
    Genre,
    Library,
    Song,
    SongRequest,
    User,
    Voice,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _make_user(email: str = "alice@example.com") -> User:
    return User.objects.create(email=email, display_name=email.split("@")[0])


def _make_library(user: User | None = None) -> Library:
    return Library.objects.create(user=user or _make_user())


# =====================================================================
# BR-02 — SongRequest prompt text must not exceed 1000 characters
# =====================================================================

class BR02PromptLengthTests(TestCase):

    def test_prompt_exactly_1000_chars_is_allowed(self):
        user = _make_user()
        sr = SongRequest(
            user=user,
            title="OK",
            genre=Genre.POP,
            prompt_text="x" * 1000,
        )
        sr.full_clean()  # must not raise

    def test_prompt_over_1000_chars_is_rejected(self):
        user = _make_user()
        sr = SongRequest(
            user=user,
            title="Too long",
            genre=Genre.POP,
            prompt_text="x" * 1001,
        )
        with self.assertRaises(ValidationError) as ctx:
            sr.full_clean()
        self.assertIn("prompt_text", ctx.exception.message_dict)


# =====================================================================
# BR-04 — Song duration must not exceed 15 minutes
# =====================================================================

class BR04DurationCapTests(TestCase):

    def setUp(self):
        self.library = _make_library()

    def _new_song(self, duration: str | None) -> Song:
        return Song(
            library=self.library,
            title="Test",
            genre=Genre.POP,
            duration=duration,
            status=GenerationStatus.SUCCESS,
        )

    def test_duration_blank_is_allowed(self):
        self._new_song(None).save()  # must not raise

    def test_duration_under_cap_is_allowed(self):
        self._new_song("14:59").save()

    def test_duration_at_cap_is_allowed(self):
        self._new_song("15:00").save()

    def test_duration_over_cap_is_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._new_song("15:01").save()
        self.assertIn("duration", ctx.exception.message_dict)
        self.assertIn("BR-04", str(ctx.exception))

    def test_duration_with_hours_segment(self):
        with self.assertRaises(ValidationError):
            self._new_song("1:00:00").save()  # 60 min — way over

    def test_duration_malformed_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._new_song("3m42s").save()  # contains letters


# =====================================================================
# BR-05 — Each User has exactly one Library (OneToOne)
# =====================================================================

class BR05OneLibraryPerUserTests(TestCase):

    def test_user_can_have_one_library(self):
        user = _make_user()
        Library.objects.create(user=user)
        self.assertEqual(Library.objects.filter(user=user).count(), 1)

    def test_second_library_for_same_user_is_rejected(self):
        user = _make_user()
        Library.objects.create(user=user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Library.objects.create(user=user)


# =====================================================================
# BR-06 — Library capacity limit (1,000,000 songs)
# =====================================================================

class BR06CapacityTests(TestCase):
    """
    The real cap is 1 million; we shrink ``CAPACITY_LIMIT`` to 2 in
    setUp so the test runs in milliseconds. The rule itself is what we
    care about, not the literal number.
    """

    def setUp(self):
        self._original = Library.CAPACITY_LIMIT
        Library.CAPACITY_LIMIT = 2
        self.library = _make_library()

    def tearDown(self):
        Library.CAPACITY_LIMIT = self._original

    def _add_song(self, title: str = "x") -> Song:
        return Song.objects.create(
            library=self.library,
            title=title,
            genre=Genre.POP,
            status=GenerationStatus.SAVED,
        )

    def test_under_capacity_allows_save(self):
        self._add_song("first")
        self._add_song("second")
        self.assertEqual(self.library.song_count, 2)
        self.assertTrue(self.library.is_at_capacity)

    def test_at_capacity_rejects_new_song(self):
        self._add_song("first")
        self._add_song("second")
        with self.assertRaises(ValidationError) as ctx:
            self._add_song("overflow")
        self.assertIn("library", ctx.exception.message_dict)
        self.assertIn("BR-06", str(ctx.exception))

    def test_updating_existing_song_does_not_trigger_capacity_check(self):
        s = self._add_song("first")
        self._add_song("second")
        self.assertTrue(self.library.is_at_capacity)
        # Updating an existing song must NOT fail capacity check.
        s.title = "renamed"
        s.save()
        self.assertEqual(Song.objects.get(pk=s.pk).title, "renamed")


# =====================================================================
# Strategy contract — Mock implementation
# =====================================================================

class MockStrategyContractTests(TestCase):

    def setUp(self):
        self.strategy = MockSongGeneratorStrategy()
        self.req = GenerationRequest(
            prompt_text="A melancholy jazz piece about rain",
            title="Rainfall",
            genre=Genre.JAZZ.value,
            voice=Voice.FEMALE.value,
        )

    def test_generate_returns_terminal_success(self):
        result = self.strategy.generate(self.req)
        self.assertIsInstance(result, GenerationResult)
        self.assertEqual(result.status, StrategyStatus.SUCCESS)
        self.assertEqual(result.progress, 100)
        self.assertTrue(result.task_id)
        self.assertTrue(result.is_terminal)
        self.assertEqual(result.strategy_name, "mock")
        self.assertTrue(result.audio_url)

    def test_get_status_replays_cached_result(self):
        first = self.strategy.generate(self.req)
        replayed = self.strategy.get_status(first.task_id)
        self.assertEqual(replayed.task_id, first.task_id)
        self.assertEqual(replayed.audio_url, first.audio_url)

    def test_get_status_unknown_id_still_returns_success(self):
        # Mock is intentionally permissive — used for offline demos.
        result = self.strategy.get_status("mock-unknown-1234")
        self.assertEqual(result.status, StrategyStatus.SUCCESS)


# =====================================================================
# View authentication — protected pages redirect anonymous users
# =====================================================================

class ProtectedViewAuthTests(TestCase):
    """
    The Create Song and Library pages must require login (FR-01 +
    Exercise 5 §3.1). Anonymous GETs should redirect to the login URL
    rather than expose the page.
    """

    def setUp(self):
        self.client = Client()

    def _assert_redirects_to_login(self, url: str):
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 302,
            f"{url} should redirect anonymous users (got {response.status_code})",
        )
        self.assertIn("login", response["Location"].lower())

    def test_create_page_requires_login(self):
        self._assert_redirects_to_login(reverse("create_song"))

    def test_library_page_requires_login(self):
        self._assert_redirects_to_login(reverse("library"))

    def test_landing_page_is_public(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)


# =====================================================================
# Smoke test — auth.User → music.User signal bridge (Exercise 5)
# =====================================================================

class AuthUserBridgeTests(TestCase):
    """
    Creating a Django ``auth.User`` should upsert a matching
    ``music.User`` via the signal in ``music/signals.py``. This keeps
    the Exercise 3 domain entity in sync with the auth subsystem
    without leaking auth concerns into the domain layer.
    """

    def test_creating_auth_user_creates_music_user(self):
        AuthUser = get_user_model()
        AuthUser.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="x",
        )
        self.assertTrue(
            User.objects.filter(email="bob@example.com").exists(),
            "Signal bridge should have upserted a music.User row",
        )
