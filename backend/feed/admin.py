from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import models


@admin.register(models.User)
class VortexUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("display_name", "avatar_url", "cover_url", "bio", "location", "website", "verified")}),
    )
    list_display = ("username", "display_name", "verified", "is_staff")


@admin.register(models.Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "caption", "created_at")
    search_fields = ("caption", "author__username")


admin.site.register(models.Follow)
admin.site.register(models.Like)
admin.site.register(models.SavedPost)
admin.site.register(models.Comment)
admin.site.register(models.Story)
admin.site.register(models.Notification)
admin.site.register(models.StoryLike)
