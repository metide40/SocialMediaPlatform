"""JSON API views. Session auth + CSRF (frontend sends X-CSRFToken)."""
import json
import re
from functools import wraps

from django.contrib.auth import authenticate, login, logout, password_validation
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, TextField
from django.db.models.functions import Cast
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_http_methods
import uuid
from pathlib import Path as FsPath

from .models import (
    Comment, Follow, Like, Notification, Post, SavedPost, Story, StoryLike, StoryView, User, story_expiry,
)
from .serializers import (
    brief_user, serialize_comment, serialize_notification, serialize_posts, serialize_story, serialize_users,
)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
URL_CHECK = URLValidator(schemes=["http", "https"])


# ---------------------------------------------------------------- helpers
def error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def read_json(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def api_login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error("Authentication required", 401)
        return view(request, *args, **kwargs)
    return wrapper


def notify(recipient, actor, kind, post=None, excerpt=""):
    if recipient.id == actor.id:
        return
    if kind in (Notification.LIKE, Notification.FOLLOW):  # avoid spam on repeated toggles
        Notification.objects.get_or_create(
            recipient=recipient, actor=actor, kind=kind, post=post,
            defaults={"excerpt": excerpt},
        )
    else:
        Notification.objects.create(recipient=recipient, actor=actor, kind=kind, post=post, excerpt=excerpt)


def post_queryset(viewer):
    return (
        Post.objects.select_related("author")
        .annotate(
            likes_count=Count("likes", distinct=True),
            is_liked=Exists(Like.objects.filter(post=OuterRef("pk"), user=viewer)),
            is_saved=Exists(SavedPost.objects.filter(post=OuterRef("pk"), user=viewer)),
        )
        .prefetch_related(Prefetch("comments", queryset=Comment.objects.select_related("user")))
    )


def clean_tags(raw):
    if isinstance(raw, str):
        raw = re.split(r"[,\s]+", raw)
    if not isinstance(raw, list):
        return []
    tags = []
    for t in raw:
        t = re.sub(r"[^\w]", "", str(t).lstrip("#"))[:30].lower()
        if t and t not in tags:
            tags.append(t)
    return tags[:10]


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def save_uploaded_image(uploaded, folder="uploads"):
    """Save an uploaded image file; return a public media URL path."""
    if not uploaded:
        return None
    content_type = getattr(uploaded, "content_type", "") or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError("Only JPEG, PNG, GIF or WebP images are allowed.")
    size = getattr(uploaded, "size", 0) or 0
    if size > MAX_IMAGE_BYTES:
        raise ValidationError("Image is too large (max 8 MB).")
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}
    ext = FsPath(get_valid_filename(uploaded.name or "image.jpg")).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        ext = ext_map.get(content_type, ".jpg")
    if ext == ".jpeg":
        ext = ".jpg"
    name = f"{folder}/{uuid.uuid4().hex}{ext}"
    saved = default_storage.save(name, uploaded)
    return default_storage.url(saved)


def resolve_image(request, data, file_field="image", url_field="imageUrl"):
    """Accept either an uploaded file or an http(s) URL. Returns URL string or raises ValidationError."""
    uploaded = request.FILES.get(file_field)
    if uploaded:
        return save_uploaded_image(uploaded)
    image_url = ""
    if data:
        image_url = str(data.get(url_field, "")).strip()
    if not image_url and request.POST.get(url_field):
        image_url = str(request.POST.get(url_field, "")).strip()
    if not image_url:
        raise ValidationError("Provide an image file or a valid image URL.")
    try:
        URL_CHECK(image_url)
    except ValidationError:
        raise ValidationError("Enter a valid http(s) image URL.")
    return image_url[:500]


def read_body(request):
    """JSON body or empty dict for multipart forms."""
    ct = (request.content_type or "").split(";")[0].strip().lower()
    if ct == "application/json":
        return read_json(request) or {}
    return {}


# ------------------------------------------------------------------- auth
@require_http_methods(["POST"])
def register(request):
    data = read_json(request)
    if data is None:
        return error("Invalid JSON")
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    display_name = str(data.get("displayName", "")).strip()[:80]
    if not USERNAME_RE.match(username):
        return error("Username must be 3-30 letters, numbers or underscores.")
    if User.objects.filter(username__iexact=username).exists():
        return error("That username is taken.", 409)
    try:
        password_validation.validate_password(password, User(username=username))
    except ValidationError as exc:
        return error(" ".join(exc.messages))
    try:
        user = User.objects.create_user(username=username, password=password, display_name=display_name)
    except IntegrityError:
        return error("That username is taken.", 409)
    login(request, user)
    return JsonResponse(serialize_users([user], user)[user.id], status=201)


@require_http_methods(["POST"])
def login_view(request):
    data = read_json(request)
    if data is None:
        return error("Invalid JSON")
    user = authenticate(request, username=str(data.get("username", "")).strip(), password=str(data.get("password", "")))
    if user is None:
        return error("Wrong username or password.", 401)
    login(request, user)
    return JsonResponse(serialize_users([user], user)[user.id])


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"ok": True})


@require_http_methods(["GET", "PATCH", "POST"])
@api_login_required
def me(request):
    if request.method == "GET":
        return JsonResponse(serialize_users([request.user], request.user)[request.user.id])

    # PATCH / POST: update profile (multipart or JSON)
    data = read_body(request)
    user = request.user

    if "displayName" in data or request.POST.get("displayName") is not None:
        name = str(data.get("displayName", request.POST.get("displayName", ""))).strip()[:80]
        user.display_name = name
    if "bio" in data or request.POST.get("bio") is not None:
        user.bio = str(data.get("bio", request.POST.get("bio", ""))).strip()[:300]
    if "location" in data or request.POST.get("location") is not None:
        user.location = str(data.get("location", request.POST.get("location", ""))).strip()[:80]
    if "website" in data or request.POST.get("website") is not None:
        user.website = str(data.get("website", request.POST.get("website", ""))).strip()[:120]

    # Avatar: file preferred, else URL
    if request.FILES.get("avatar"):
        try:
            user.avatar_url = save_uploaded_image(request.FILES["avatar"], folder="avatars")
        except ValidationError as e:
            return error(e.messages[0] if getattr(e, "messages", None) else str(e))
    elif data.get("avatarUrl") or request.POST.get("avatarUrl"):
        url = str(data.get("avatarUrl") or request.POST.get("avatarUrl") or "").strip()
        if url:
            try:
                URL_CHECK(url)
            except ValidationError:
                return error("Enter a valid http(s) avatar URL.")
            user.avatar_url = url[:500]
        else:
            user.avatar_url = ""

    if request.FILES.get("cover"):
        try:
            user.cover_url = save_uploaded_image(request.FILES["cover"], folder="covers")
        except ValidationError as e:
            return error(e.messages[0] if getattr(e, "messages", None) else str(e))
    elif data.get("coverUrl") or request.POST.get("coverUrl"):
        url = str(data.get("coverUrl") or request.POST.get("coverUrl") or "").strip()
        if url:
            try:
                URL_CHECK(url)
            except ValidationError:
                return error("Enter a valid http(s) cover URL.")
            user.cover_url = url[:500]
        else:
            user.cover_url = ""

    user.save()
    return JsonResponse(serialize_users([user], user)[user.id])


# ------------------------------------------------------------------ users
@require_http_methods(["GET"])
@api_login_required
def user_detail(request, username):
    user = get_object_or_404(User, username__iexact=username)
    return JsonResponse(serialize_users([user], request.user)[user.id])


@require_http_methods(["POST"])
@api_login_required
def toggle_follow(request, username):
    target = get_object_or_404(User, username__iexact=username)
    if target.id == request.user.id:
        return error("You can't follow yourself.")
    rel, created = Follow.objects.get_or_create(follower=request.user, following=target)
    if created:
        notify(target, request.user, Notification.FOLLOW)
    else:
        rel.delete()
    return JsonResponse({
        "isFollowing": created,
        "followersCount": Follow.objects.filter(following=target).count(),
        "followingCount": Follow.objects.filter(follower=request.user).count(),
    })


# ------------------------------------------------------------------ posts
@require_http_methods(["GET", "POST"])
@api_login_required
def posts(request):
    viewer = request.user

    if request.method == "POST":
        data = read_body(request)
        # multipart fields fall back to POST
        try:
            image_url = resolve_image(request, data)
        except ValidationError as e:
            return error(e.messages[0] if getattr(e, "messages", None) else str(e))
        caption = str(data.get("caption") or request.POST.get("caption") or "").strip()[:500]
        location = str(data.get("location") or request.POST.get("location") or "").strip()[:80]
        tags_raw = data.get("tags", request.POST.get("tags", []))
        post = Post.objects.create(
            author=viewer,
            image_url=image_url[:500],
            caption=caption,
            location=location,
            tags=clean_tags(tags_raw),
        )
        full = post_queryset(viewer).get(pk=post.pk)
        return JsonResponse(serialize_posts([full], viewer)[0], status=201)

    qs = post_queryset(viewer)
    mode = request.GET.get("filter", "for-you")
    author = request.GET.get("author", "").strip()
    q = request.GET.get("q", "").strip()[:100]

    if author:
        qs = qs.filter(author__username__iexact=author)
    elif mode == "saved":
        qs = qs.filter(is_saved=True)
    elif mode == "liked":
        qs = qs.filter(is_liked=True)
    elif mode == "following":
        followed = Follow.objects.filter(follower=viewer).values("following_id")
        qs = qs.filter(Q(author_id__in=followed) | Q(author=viewer))

    if q:
        qs = qs.annotate(tags_text=Cast("tags", output_field=TextField())).filter(
            Q(caption__icontains=q) | Q(author__username__icontains=q)
            | Q(author__display_name__icontains=q) | Q(location__icontains=q)
            | Q(tags_text__icontains=q)
        )

    qs = qs.order_by("-likes_count", "-created_at") if (mode == "explore" and not author) else qs.order_by("-created_at")

    try:
        limit = max(1, min(int(request.GET.get("limit", 30)), 50))
        offset = max(0, int(request.GET.get("offset", 0)))
    except ValueError:
        return error("limit/offset must be integers")
    page = list(qs[offset:offset + limit + 1])
    has_more = len(page) > limit
    return JsonResponse({"results": serialize_posts(page[:limit], viewer), "hasMore": has_more})


@require_http_methods(["POST"])
@api_login_required
def toggle_like(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    like, created = Like.objects.get_or_create(user=request.user, post=post)
    if created:
        notify(post.author, request.user, Notification.LIKE, post=post)
    else:
        like.delete()
    return JsonResponse({"isLiked": created, "likesCount": Like.objects.filter(post=post).count()})


@require_http_methods(["POST"])
@api_login_required
def toggle_save(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    saved, created = SavedPost.objects.get_or_create(user=request.user, post=post)
    if not created:
        saved.delete()
    return JsonResponse({"isSaved": created})


@require_http_methods(["POST"])
@api_login_required
def add_comment(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    data = read_json(request)
    if data is None:
        return error("Invalid JSON")
    content = str(data.get("content", "")).strip()
    if not content:
        return error("Comment can't be empty.")
    if len(content) > 500:
        return error("Comment is too long (500 max).")
    comment = Comment.objects.create(post=post, user=request.user, content=content)
    notify(post.author, request.user, Notification.COMMENT, post=post, excerpt=content[:100])
    return JsonResponse(serialize_comment(comment), status=201)


# ---------------------------------------------------------------- stories
@require_http_methods(["GET", "POST"])
@api_login_required
def stories(request):
    me_ = request.user

    if request.method == "POST":
        data = read_body(request)
        text = str(data.get("text") or request.POST.get("text") or "").strip()[:300]
        uploaded = request.FILES.get("image")
        raw_url = str(data.get("imageUrl") or request.POST.get("imageUrl") or "").strip()
        image_url = ""
        if uploaded or raw_url:
            try:
                image_url = resolve_image(request, data)
            except ValidationError as e:
                return error(e.messages[0] if getattr(e, "messages", None) else str(e))
        if not image_url and not text:
            return error("Add a photo or some text for your story.")
        story = Story.objects.create(user=me_, image_url=(image_url or "")[:500], text=text)
        story.seen = False
        story.likes_count = 0
        story.is_liked = False
        return JsonResponse(serialize_story(story), status=201)

    followed = Follow.objects.filter(follower=me_).values("following_id")
    qs = (
        Story.objects.filter(created_at__gte=story_expiry())
        .filter(Q(user=me_) | Q(user_id__in=followed))
        .select_related("user")
        .annotate(
            seen=Exists(StoryView.objects.filter(story=OuterRef("pk"), user=me_)),
            likes_count=Count("likes", distinct=True),
            is_liked=Exists(StoryLike.objects.filter(story=OuterRef("pk"), user=me_)),
        )
        .order_by("created_at")
    )
    return JsonResponse({"results": [serialize_story(s) for s in qs]})


def get_visible_story(user, story_id):
    """Unexpired story visible to `user` (their own + people they follow), else 404.
    Same rule as the stories feed."""
    story = get_object_or_404(Story, pk=story_id, created_at__gte=story_expiry())
    if story.user_id != user.id and not Follow.objects.filter(follower=user, following_id=story.user_id).exists():
        raise Http404("Story not found.")
    return story


@require_http_methods(["POST"])
@api_login_required
def story_seen(request, story_id):
    story = get_visible_story(request.user, story_id)
    StoryView.objects.get_or_create(user=request.user, story=story)
    return JsonResponse({"seen": True})


@require_http_methods(["POST"])
@api_login_required
def toggle_story_like(request, story_id):
    story = get_visible_story(request.user, story_id)
    like, created = StoryLike.objects.get_or_create(user=request.user, story=story)
    if not created:
        like.delete()
    return JsonResponse({
        "isLiked": created,
        "likesCount": StoryLike.objects.filter(story=story).count(),
    })


@require_http_methods(["GET"])
@api_login_required
def story_likes(request, story_id):
    """Who liked this story (and return the story payload so the client can open it)."""
    story = get_object_or_404(
        Story.objects.select_related("user").annotate(
            likes_count=Count("likes", distinct=True),
            is_liked=Exists(StoryLike.objects.filter(story=OuterRef("pk"), user=request.user)),
            seen=Exists(StoryView.objects.filter(story=OuterRef("pk"), user=request.user)),
        ),
        pk=story_id,
        created_at__gte=story_expiry(),
    )
    # Same visibility as the stories feed: your own stories + people you follow.
    me = request.user
    if story.user_id != me.id:
        if not Follow.objects.filter(follower=me, following_id=story.user_id).exists():
            return error("Story not found.", 404)
    likes = (
        StoryLike.objects.filter(story=story)
        .select_related("user")
        .order_by("-created_at")[:100]
    )
    return JsonResponse({
        "story": serialize_story(story),
        "results": [brief_user(like.user) for like in likes],
    })


# ---------------------------------------------------------- notifications
@require_http_methods(["GET"])
@api_login_required
def notifications(request):
    qs = Notification.objects.filter(recipient=request.user).select_related("actor")[:30]
    items = [serialize_notification(n) for n in qs]
    return JsonResponse({
        "results": items,
        "unreadCount": Notification.objects.filter(recipient=request.user, unread=True).count(),
    })


@require_http_methods(["POST"])
@api_login_required
def notifications_read(request):
    Notification.objects.filter(recipient=request.user, unread=True).update(unread=False)
    return JsonResponse({"ok": True})


@require_http_methods(["DELETE", "POST"])
@api_login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.author_id != request.user.id:
        return error("You can only delete your own posts.", 403)
    post.delete()
    return JsonResponse({"ok": True})
