"""
URL configuration for cithara_project project.

Routing overview
----------------
* ``/``              → Web UI (Landing, Create Song, Library, Share) — ``music.web_urls``
* ``/api/``          → REST API from Exercise 3 / 4 — ``music.urls``
* ``/accounts/``     → django-allauth (Google OAuth login callbacks) — SRS FR-01
* ``/admin/``        → Django admin
"""

from django.contrib import admin
from django.urls import path, include

# Admin site customization
admin.site.site_header = "CITHARA Admin"
admin.site.site_title = "CITHARA - AI Music Generator"
admin.site.index_title = "Domain Management"

urlpatterns = [
    path('admin/', admin.site.urls),

    # django-allauth endpoints (login, logout, Google callback, etc.)
    path('accounts/', include('allauth.urls')),

    # REST API (Exercise 3 / 4)
    path('api/', include('music.urls')),

    # Web UI (Exercise 5 — SRS §3.1)
    path('', include('music.web_urls')),
]
