"""
CITHARA Domain Layer - Django Admin Configuration

Provides CRUD operations for all domain entities via Django Admin interface.
This satisfies Exercise 3 Task 4: Demonstrate Create, Read, Update, Delete
operations for core domain entities.
"""

from django.contrib import admin
from .models import User, Library, Song, SongRequest, GenerationJob, ShareLink


# =============================================================================
# Inline Models (for nested display)
# =============================================================================

class LibraryInline(admin.StackedInline):
    """Display Library inline within User admin."""
    model = Library
    extra = 0
    readonly_fields = ('library_id', 'created_at')
    can_delete = False


class SongInline(admin.TabularInline):
    """Display Songs inline within Library admin."""
    model = Song
    extra = 0
    readonly_fields = ('song_id', 'created_at')
    fields = ('song_id', 'title', 'genre', 'status', 'duration', 'created_at')


class GenerationJobInline(admin.TabularInline):
    """Display GenerationJobs inline within SongRequest admin."""
    model = GenerationJob
    extra = 0
    readonly_fields = ('job_id', 'created_at', 'completed_at')
    fields = ('job_id', 'status', 'progress', 'song', 'error_message', 'created_at', 'completed_at')


class ShareLinkInline(admin.TabularInline):
    """Display ShareLinks inline within Song admin."""
    model = ShareLink
    extra = 0
    readonly_fields = ('share_link_id', 'token', 'created_at')
    fields = ('share_link_id', 'token', 'created_by', 'is_active', 'access_count', 'created_at')


# =============================================================================
# Model Admin Classes
# =============================================================================

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """
    Admin interface for User entity.
    CRUD: Create, Read, Update, Delete users.
    """
    list_display = ('display_name', 'email', 'google_id', 'created_at')
    search_fields = ('display_name', 'email', 'google_id')
    list_filter = ('created_at',)
    readonly_fields = ('user_id', 'created_at')
    inlines = [LibraryInline]
    fieldsets = (
        ('User Information', {
            'fields': ('user_id', 'email', 'display_name')
        }),
        ('Authentication', {
            'fields': ('google_id', 'password'),
            'description': 'Google OAuth ID and optional manual login password (FR-06, A4)'
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )


@admin.register(Library)
class LibraryAdmin(admin.ModelAdmin):
    """
    Admin interface for Library entity.
    CRUD: Create, Read, Update, Delete libraries.
    Shows song count and capacity status (BR-06).
    """
    list_display = ('library_id', 'user', 'get_song_count', 'created_at')
    search_fields = ('user__display_name', 'user__email')
    readonly_fields = ('library_id', 'created_at', 'get_song_count', 'get_capacity_status')
    inlines = [SongInline]

    @admin.display(description='Song Count')
    def get_song_count(self, obj):
        return obj.song_count

    @admin.display(description='At Capacity (BR-06)')
    def get_capacity_status(self, obj):
        return f"{'YES - FULL' if obj.is_at_capacity else 'No'} ({obj.song_count:,} / {obj.CAPACITY_LIMIT:,})"


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    """
    Admin interface for Song entity.
    CRUD: Create, Read, Update, Delete songs.
    """
    list_display = ('title', 'genre', 'status', 'get_owner', 'duration', 'created_at')
    search_fields = ('title', 'library__user__display_name')
    list_filter = ('genre', 'status', 'created_at')
    readonly_fields = ('song_id', 'created_at')
    inlines = [ShareLinkInline]
    fieldsets = (
        ('Song Information', {
            'fields': ('song_id', 'library', 'title', 'genre')
        }),
        ('Audio', {
            'fields': ('audio_file_url', 'duration', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )

    @admin.display(description='Owner')
    def get_owner(self, obj):
        return obj.library.user.display_name


@admin.register(SongRequest)
class SongRequestAdmin(admin.ModelAdmin):
    """
    Admin interface for SongRequest entity.
    CRUD: Create, Read, Update, Delete song requests.
    """
    list_display = ('title', 'user', 'genre', 'voice', 'mood', 'occasion', 'created_at')
    search_fields = ('title', 'user__display_name', 'prompt_text')
    list_filter = ('genre', 'voice', 'created_at')
    readonly_fields = ('request_id', 'created_at')
    inlines = [GenerationJobInline]
    fieldsets = (
        ('Request Details', {
            'fields': ('request_id', 'user', 'title', 'genre')
        }),
        ('Optional Parameters', {
            'fields': ('voice', 'occasion', 'mood')
        }),
        ('Prompt', {
            'fields': ('prompt_text',),
            'description': 'Max 1000 characters (BR-02, FR-09)'
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    """
    Admin interface for GenerationJob entity.
    CRUD: Create, Read, Update, Delete generation jobs.
    """
    list_display = ('job_id', 'get_request_title', 'status', 'progress', 'song', 'created_at', 'completed_at')
    search_fields = ('song_request__title', 'song_request__user__display_name')
    list_filter = ('status', 'created_at')
    readonly_fields = ('job_id', 'created_at')
    fieldsets = (
        ('Job Information', {
            'fields': ('job_id', 'song_request', 'song')
        }),
        ('Progress', {
            'fields': ('status', 'progress')
        }),
        ('Error Handling', {
            'fields': ('error_message',),
            'description': 'Error details if generation failed (FR-17)'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at')
        }),
    )

    @admin.display(description='Request Title')
    def get_request_title(self, obj):
        return obj.song_request.title


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    """
    Admin interface for ShareLink entity.
    CRUD: Create, Read, Update, Delete share links.
    """
    list_display = ('share_link_id', 'song', 'created_by', 'is_active', 'access_count', 'created_at')
    search_fields = ('token', 'song__title', 'created_by__display_name')
    list_filter = ('is_active', 'created_at')
    readonly_fields = ('share_link_id', 'token', 'created_at')
    fieldsets = (
        ('Link Information', {
            'fields': ('share_link_id', 'token', 'song', 'created_by')
        }),
        ('Status', {
            'fields': ('is_active', 'access_count'),
            'description': 'Active/inactive for revocation (NFR-SEC-05, A2)'
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )
