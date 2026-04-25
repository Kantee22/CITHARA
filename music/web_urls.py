"""
URL configuration — Web UI (Exercise 5).

Separated from the REST ``music/urls.py`` so the two concerns stay
loosely coupled: the API layer can evolve independently of the
user-facing pages.
"""

from django.urls import path

from . import web_views

urlpatterns = [
    # --- Public ------------------------------------------------------
    path('', web_views.landing, name='landing'),
    path('share/<uuid:token>/', web_views.share_public, name='share_public'),
    path('share/<uuid:token>/download/', web_views.share_download, name='share_download'),

    # --- Authenticated pages -----------------------------------------
    path('create/', web_views.create_song, name='create_song'),
    path('create/submit/', web_views.create_song_submit, name='create_song_submit'),
    path('create/poll/<uuid:job_id>/', web_views.create_song_poll, name='create_song_poll'),
    path('create/save/<uuid:song_id>/', web_views.create_song_save, name='create_song_save'),
    path('create/discard/<uuid:song_id>/', web_views.create_song_discard, name='create_song_discard'),
    path('create/regenerate/<uuid:song_id>/', web_views.create_song_regenerate, name='create_song_regenerate'),

    path('library/', web_views.library, name='library'),
    path('library/<uuid:song_id>/delete/', web_views.library_delete, name='library_delete'),
    path('library/<uuid:song_id>/share/', web_views.library_share, name='library_share'),
    path('library/<uuid:song_id>/download/', web_views.library_download, name='library_download'),
]
