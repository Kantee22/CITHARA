"""
Signal bridge between ``django.contrib.auth.User`` and ``music.User``.

Option A (see README): we intentionally keep ``music.User`` — the domain
entity from Exercise 2/3 — separate from Django's built-in auth user so
the prior exercises' evidence stays intact. This module wires the two
tables together so the user never has to think about the split:

* When a visitor signs in with Google, django-allauth creates/updates
  a ``auth.User`` row. The ``user_signed_up`` / ``social_account_added``
  signals then populate (or refresh) the matching ``music.User`` with
  ``email`` / ``display_name`` / ``google_id``.
* A safety-net ``post_save`` on ``auth.User`` covers the manual
  ``createsuperuser`` path so admin accounts get a ``music.User`` too.

Application code always looks up the music-side row via
:func:`get_music_user_for` — never by email directly — so the mapping
can be extended later without touching every caller.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User as DomainUser, Library

logger = logging.getLogger(__name__)

AuthUser = get_user_model()


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def get_music_user_for(auth_user) -> Optional[DomainUser]:
    """
    Return the ``music.User`` paired with ``auth_user``.

    Lookup is by email (case-insensitive) because that's the only
    field both sides are guaranteed to share. Returns ``None`` when
    no match exists (e.g. anonymous request, stale session).
    """
    if not getattr(auth_user, "is_authenticated", False):
        return None
    email = (getattr(auth_user, "email", "") or "").strip().lower()
    if not email:
        return None
    return DomainUser.objects.filter(email__iexact=email).first()


def _ensure_music_user(
    *,
    email: str,
    display_name: str,
    google_id: Optional[str] = None,
) -> DomainUser:
    """
    Upsert a ``music.User`` row with the given fields.

    Also makes sure the user has a ``Library`` (BR-05 — every user
    owns exactly one library) so the first Create-Song flow never
    crashes on a missing FK.
    """
    email = email.strip().lower()
    domain_user, created = DomainUser.objects.get_or_create(
        email=email,
        defaults={
            "display_name": display_name or email.split("@")[0],
            "google_id": google_id,
        },
    )

    # Refresh metadata that Google may have updated.
    dirty = False
    if display_name and domain_user.display_name != display_name:
        domain_user.display_name = display_name
        dirty = True
    if google_id and domain_user.google_id != google_id:
        domain_user.google_id = google_id
        dirty = True
    if dirty:
        domain_user.save()

    # BR-05: one library per user.
    Library.objects.get_or_create(user=domain_user)

    if created:
        logger.info("music.User created for %s (google_id=%s)", email, bool(google_id))
    return domain_user


# ---------------------------------------------------------------------------
# allauth signals — primary path for Google logins
# ---------------------------------------------------------------------------
# We import lazily inside the handlers so the module is safe to import
# even in test environments where allauth is not installed.

try:
    from allauth.account.signals import user_signed_up, user_logged_in
    from allauth.socialaccount.signals import social_account_added, social_account_updated
    _ALLAUTH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ALLAUTH_AVAILABLE = False


if _ALLAUTH_AVAILABLE:

    def _extract_google_info(sociallogin):
        """Pull display name + google_id out of an allauth SocialLogin."""
        extra = getattr(sociallogin.account, "extra_data", {}) or {}
        display = extra.get("name") or extra.get("given_name") or ""
        google_id = str(extra.get("sub") or sociallogin.account.uid or "")
        return display, google_id

    @receiver(user_signed_up)
    def _on_user_signed_up(sender, request, user, **kwargs):
        """First-time signup via any provider (Google in our case)."""
        sociallogin = kwargs.get("sociallogin")
        display_name = user.get_full_name() or user.username or user.email
        google_id = None
        if sociallogin is not None:
            display_name, google_id = _extract_google_info(sociallogin)
        _ensure_music_user(
            email=user.email,
            display_name=display_name or user.email,
            google_id=google_id,
        )

    @receiver(user_logged_in)
    def _on_user_logged_in(sender, request, user, **kwargs):
        """Defensive: keep the mapping alive for every login, not just signup."""
        sociallogin = kwargs.get("sociallogin")
        display_name = user.get_full_name() or user.username or user.email
        google_id = None
        if sociallogin is not None:
            display_name, google_id = _extract_google_info(sociallogin)
        _ensure_music_user(
            email=user.email,
            display_name=display_name or user.email,
            google_id=google_id,
        )

    @receiver(social_account_added)
    @receiver(social_account_updated)
    def _on_social_account_touched(sender, request, sociallogin, **kwargs):
        """Connect/reconnect Google → refresh google_id on the domain row."""
        user = sociallogin.user
        display_name, google_id = _extract_google_info(sociallogin)
        _ensure_music_user(
            email=user.email,
            display_name=display_name or user.email,
            google_id=google_id,
        )


# ---------------------------------------------------------------------------
# Safety net — covers ``createsuperuser`` and any non-allauth path
# ---------------------------------------------------------------------------

@receiver(post_save, sender=AuthUser)
def _mirror_auth_user(sender, instance, created, **kwargs):
    """
    Ensure every ``auth.User`` has a matching ``music.User``.

    Skips rows without an email (shouldn't happen for Google logins,
    but ``createsuperuser`` can create them).
    """
    if not instance.email:
        return
    display_name = instance.get_full_name() or instance.username or instance.email
    _ensure_music_user(
        email=instance.email,
        display_name=display_name,
        google_id=None,  # populated later by the allauth signals above
    )
