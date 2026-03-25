"""
CITHARA Domain Layer - URL Configuration

Maps API endpoints to views for CRUD operations on all domain entities.
"""

from django.urls import path
from . import views

urlpatterns = [
    # User endpoints
    path('users/', views.user_list, name='user-list'),
    path('users/<uuid:user_id>/', views.user_detail, name='user-detail'),

    # Library endpoints
    path('libraries/', views.library_list, name='library-list'),
    path('libraries/<uuid:library_id>/', views.library_detail, name='library-detail'),

    # Song endpoints
    path('songs/', views.song_list, name='song-list'),
    path('songs/<uuid:song_id>/', views.song_detail, name='song-detail'),

    # SongRequest endpoints
    path('song-requests/', views.song_request_list, name='song-request-list'),
    path('song-requests/<uuid:request_id>/', views.song_request_detail, name='song-request-detail'),

    # GenerationJob endpoints
    path('generation-jobs/', views.generation_job_list, name='generation-job-list'),
    path('generation-jobs/<uuid:job_id>/', views.generation_job_detail, name='generation-job-detail'),

    # ShareLink endpoints
    path('share-links/', views.share_link_list, name='share-link-list'),
    path('share-links/<uuid:share_link_id>/', views.share_link_detail, name='share-link-detail'),
]
