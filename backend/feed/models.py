from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class User(AbstractUser):
    display_name = models.CharField(max_length=80, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)
    cover_url = models.URLField(max_length=500, blank=True)
    bio = models.TextField(max_length=300, blank=True)
    location = models.CharField(max_length=80, blank=True)
    website = models.CharField(max_length=120, blank=True)
    verified = models.BooleanField(default=False)

    @property
    def name(self):
        return self.display_name or self.username


class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name="following_set")
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follower_set")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="unique_follow"),
            models.CheckConstraint(condition=~Q(follower=F("following")), name="no_self_follow"),
        ]

    def __str__(self):
        return f"{self.follower} -> {self.following}"


class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    image_url = models.URLField(max_length=500)
    caption = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=80, blank=True)
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Post {self.pk} by {self.author}"


class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="likes")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_like")]


class SavedPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_posts")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="saves")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "post"], name="unique_save")]


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    content = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]


def story_expiry():
    return timezone.now() - timedelta(hours=24)


class Story(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stories")
    image_url = models.URLField(max_length=500, blank=True)
    text = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name_plural = "stories"

    def __str__(self):
        return f"Story {self.pk} by {self.user}"


class StoryView(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="story_views")
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="views")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "story"], name="unique_story_view")]


class StoryLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="story_likes")
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="likes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "story"], name="unique_story_like")]


class Notification(models.Model):
    LIKE, FOLLOW, COMMENT = "like", "follow", "comment"
    KINDS = [(LIKE, "Like"), (FOLLOW, "Follow"), (COMMENT, "Comment")]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=10, choices=KINDS)
    post = models.ForeignKey(Post, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    excerpt = models.CharField(max_length=120, blank=True)
    unread = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
