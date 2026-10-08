"""Plain-dict serializers. Keys are camelCase to match the JS frontend."""
from collections import defaultdict

from django.db.models import Count
from django.utils import timezone

from .models import Follow, Notification, Post


def short_age(dt):
    secs = int((timezone.now() - dt).total_seconds())
    if secs < 60:
        return "now"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    if secs < 7 * 86400:
        return f"{secs // 86400}d"
    return f"{secs // (7 * 86400)}w"


def brief_user(u):
    return {"id": u.id, "name": u.name, "username": u.username, "avatar": u.avatar_url}


def serialize_users(users, viewer):
    """Return {user_id: profile dict} using a fixed number of queries."""
    users = list({u.id: u for u in users}.values())
    ids = [u.id for u in users]
    followers = dict(Follow.objects.filter(following_id__in=ids).order_by().values_list("following_id").annotate(c=Count("id")))
    following = dict(Follow.objects.filter(follower_id__in=ids).order_by().values_list("follower_id").annotate(c=Count("id")))
    posts = dict(Post.objects.filter(author_id__in=ids).order_by().values_list("author_id").annotate(c=Count("id")))
    followed_by_me = set(
        Follow.objects.filter(follower=viewer, following_id__in=ids).values_list("following_id", flat=True)
    )
    out = {}
    for u in users:
        out[u.id] = {
            **brief_user(u),
            "coverImage": u.cover_url,
            "bio": u.bio,
            "location": u.location,
            "website": u.website,
            "verified": u.verified,
            "followersCount": followers.get(u.id, 0),
            "followingCount": following.get(u.id, 0),
            "postsCount": posts.get(u.id, 0),
            "isFollowing": u.id in followed_by_me,
            "isMe": u.id == viewer.id,
        }
    return out


def serialize_comment(c):
    return {
        "id": c.id,
        "user": brief_user(c.user),
        "content": c.content,
        "timestamp": short_age(c.created_at),
        "createdAt": c.created_at.isoformat(),
    }


def serialize_posts(posts, viewer):
    """`posts` must come from views.post_queryset() (annotated + prefetched)."""
    posts = list(posts)
    users = serialize_users([p.author for p in posts], viewer)
    return [
        {
            "id": p.id,
            "author": users[p.author_id],
            "imageUrl": p.image_url,
            "caption": p.caption,
            "tags": p.tags or [],
            "location": p.location,
            "likesCount": p.likes_count,
            "isLiked": p.is_liked,
            "isSaved": p.is_saved,
            "comments": [serialize_comment(c) for c in p.comments.all()],
            "timestamp": short_age(p.created_at),
            "createdAt": p.created_at.isoformat(),
        }
        for p in posts
    ]


def serialize_story(s):
    return {
        "id": s.id,
        "user": brief_user(s.user),
        "previewImage": s.image_url or "",
        "text": getattr(s, "text", "") or "",
        "seen": bool(getattr(s, "seen", False)),
        "likesCount": int(getattr(s, "likes_count", 0) or 0),
        "isLiked": bool(getattr(s, "is_liked", False)),
        "createdAt": s.created_at.isoformat(),
    }


def serialize_notification(n):
    name = n.actor.name
    if n.kind == Notification.LIKE:
        text = f"{name} liked your post"
    elif n.kind == Notification.FOLLOW:
        text = f"{name} started following you"
    else:
        text = f"{name} commented: \u201c{n.excerpt}\u201d"
    return {
        "id": n.id,
        "text": text,
        "avatar": n.actor.avatar_url,
        "actor": n.actor.username,
        "timestamp": short_age(n.created_at),
        "unread": n.unread,
    }
