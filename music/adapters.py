"""
django-allauth adapters for CITHARA.

The default ``django.contrib.auth.User`` model requires a non-empty
``username`` field, but Google OAuth only gives us an email and a
display name. allauth therefore renders an intermediate "Sign Up"
form asking the user to pick a username — which breaks the SRS flow
"sign in with Google → land on Create Song" (FR-01 / FR-02).

The adapter below short-circuits that prompt by auto-generating a
unique username from the email's local-part the very first time we
see a Google account. Combined with ``SOCIALACCOUNT_AUTO_SIGNUP=True``
in settings, this makes the OAuth dance fully one-click.
"""

from __future__ import annotations

import uuid

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model


class CitharaSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Auto-fills ``user.username`` so the signup form never appears."""

    def is_auto_signup_allowed(self, request, sociallogin):
        """
        Always allow auto-signup.

        allauth's default refuses auto-signup whenever an existing
        ``auth.User`` already has a matching email — which would force
        the user to fill in the intermediate "Sign Up" form. For our
        single-tenant course project that prompt adds nothing: Google
        has already verified the email, so we trust it and either log
        the existing user in (via ``SOCIALACCOUNT_EMAIL_AUTHENTICATION``)
        or create a fresh one through ``populate_user`` below.
        """
        return True

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        # ``user.username`` is "" for fresh signups via Google. We
        # synthesise one from the email's local-part, falling back to
        # a random hex blob if the email is missing for some reason.
        if not getattr(user, "username", None):
            email = (data.get("email") or getattr(user, "email", "") or "").strip().lower()
            base = email.split("@")[0] if email else f"user{uuid.uuid4().hex[:8]}"
            # Strip characters Django's UsernameValidator rejects.
            base = "".join(ch for ch in base if ch.isalnum() or ch in "._-+") or "user"

            User = get_user_model()
            candidate = base
            suffix = 1
            while User.objects.filter(username=candidate).exists():
                suffix += 1
                candidate = f"{base}{suffix}"
            user.username = candidate

        # Make sure first/last names from Google land on the auth.User
        # so admin pages render something nicer than a hex username.
        extra = sociallogin.account.extra_data or {}
        if not user.first_name and extra.get("given_name"):
            user.first_name = extra["given_name"]
        if not user.last_name and extra.get("family_name"):
            user.last_name = extra["family_name"]

        return user
