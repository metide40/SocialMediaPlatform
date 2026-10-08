"""Automated tests for the Vortex API. Run with:  python manage.py test"""
import json
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from .models import Comment, Follow, Like, Notification, Post, Story, StoryLike, User

PASSWORD = "S3cure!pass99"
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d"
    "49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)


def post_json(client, url, data=None):
    return client.post(url, json.dumps(data or {}), content_type="application/json")


class ApiTestCase(TestCase):
    """Creates two logged-in users: alice (self.a) and bob (self.b)."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password=PASSWORD, display_name="Alice")
        self.bob = User.objects.create_user("bob", password=PASSWORD, display_name="Bob")
        self.a, self.b = Client(), Client()
        self.a.force_login(self.alice)
        self.b.force_login(self.bob)

    def make_post(self, author=None, **kw):
        return Post.objects.create(
            author=author or self.alice, image_url=kw.pop("image_url", "https://example.com/p.jpg"), **kw
        )


# ------------------------------------------------------------------ auth / profiles
class AuthAndProfileTests(ApiTestCase):
    def test_register_logs_in_and_returns_profile(self):
        c = Client()
        r = post_json(c, "/api/auth/register", {"username": "newuser", "password": PASSWORD, "displayName": "New"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(c.get("/api/me").json()["username"], "newuser")

    def test_duplicate_username_is_case_insensitive(self):
        r = post_json(Client(), "/api/auth/register", {"username": "ALICE", "password": PASSWORD})
        self.assertEqual(r.status_code, 409)

    def test_weak_password_rejected(self):
        r = post_json(Client(), "/api/auth/register", {"username": "weakguy", "password": "123"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_username_rejected(self):
        r = post_json(Client(), "/api/auth/register", {"username": "no spaces!", "password": PASSWORD})
        self.assertEqual(r.status_code, 400)

    def test_login_success_and_failure(self):
        self.assertEqual(post_json(Client(), "/api/auth/login", {"username": "alice", "password": PASSWORD}).status_code, 200)
        self.assertEqual(post_json(Client(), "/api/auth/login", {"username": "alice", "password": "wrong"}).status_code, 401)

    def test_logout_ends_session(self):
        post_json(self.a, "/api/auth/logout")
        self.assertEqual(self.a.get("/api/me").status_code, 401)

    def test_api_requires_authentication(self):
        anon = Client()
        for url in ("/api/me", "/api/posts", "/api/stories", "/api/notifications", "/api/users/alice"):
            self.assertEqual(anon.get(url).status_code, 401, url)

    def test_edit_profile(self):
        r = post_json(self.a, "/api/me", {"displayName": "Alice 2", "bio": "Hello", "location": "Adama"})
        self.assertEqual(r.status_code, 200)
        self.alice.refresh_from_db()
        self.assertEqual((self.alice.display_name, self.alice.bio, self.alice.location), ("Alice 2", "Hello", "Adama"))

    def test_edit_profile_rejects_bad_avatar_url(self):
        r = post_json(self.a, "/api/me", {"avatarUrl": "javascript:alert(1)"})
        self.assertEqual(r.status_code, 400)

    def test_view_other_profile_and_404(self):
        r = self.a.get("/api/users/bob")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["isMe"])
        self.assertEqual(self.a.get("/api/users/nobody").status_code, 404)

    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True)
        c.get("/")
        r = c.post("/api/auth/login", json.dumps({"username": "alice", "password": PASSWORD}), content_type="application/json")
        self.assertEqual(r.status_code, 403)


# -------------------------------------------------------------------------- posts
class PostTests(ApiTestCase):
    def test_create_post_with_url_and_clean_tags(self):
        r = post_json(self.a, "/api/posts", {"imageUrl": "https://example.com/a.jpg", "caption": "hi", "tags": "#One #two"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["tags"], ["one", "two"])

    def test_create_post_requires_image(self):
        self.assertEqual(post_json(self.a, "/api/posts", {"caption": "no image"}).status_code, 400)

    def test_create_post_rejects_non_http_url(self):
        self.assertEqual(post_json(self.a, "/api/posts", {"imageUrl": "javascript:alert(1)"}).status_code, 400)

    def test_create_post_with_file_upload(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            f = SimpleUploadedFile("t.png", TINY_PNG, content_type="image/png")
            r = self.a.post("/api/posts", {"image": f, "caption": "uploaded"})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["imageUrl"].startswith("/media/uploads/"))

    def test_non_image_upload_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            f = SimpleUploadedFile("evil.html", b"<script>", content_type="text/html")
            r = self.a.post("/api/posts", {"image": f})
        self.assertEqual(r.status_code, 400)

    def test_feed_filter_by_author_and_search(self):
        p = self.make_post(caption="learning django", tags=["django"])
        self.make_post(author=self.bob, caption="other")
        by_author = self.a.get("/api/posts?author=alice").json()["results"]
        self.assertEqual([x["id"] for x in by_author], [p.id])
        by_tag = self.a.get("/api/posts?q=django").json()["results"]
        self.assertEqual([x["id"] for x in by_tag], [p.id])

    def test_bad_limit_returns_400(self):
        self.assertEqual(self.a.get("/api/posts?limit=abc").status_code, 400)

    def test_pagination_has_more(self):
        for _ in range(3):
            self.make_post()
        d = self.a.get("/api/posts?limit=2").json()
        self.assertEqual(len(d["results"]), 2)
        self.assertTrue(d["hasMore"])

    def test_only_owner_can_delete_post(self):
        p = self.make_post()
        self.assertEqual(post_json(self.b, f"/api/posts/{p.id}/delete").status_code, 403)
        self.assertTrue(Post.objects.filter(pk=p.id).exists())
        self.assertEqual(post_json(self.a, f"/api/posts/{p.id}/delete").status_code, 200)
        self.assertFalse(Post.objects.filter(pk=p.id).exists())

    def test_deleting_post_cascades_comments_and_likes(self):
        p = self.make_post()
        Comment.objects.create(post=p, user=self.bob, content="hi")
        Like.objects.create(post=p, user=self.bob)
        p.delete()
        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(Like.objects.count(), 0)

    def test_save_toggle_and_saved_filter(self):
        p = self.make_post(author=self.bob)
        self.assertTrue(post_json(self.a, f"/api/posts/{p.id}/save").json()["isSaved"])
        saved = self.a.get("/api/posts?filter=saved").json()["results"]
        self.assertEqual([x["id"] for x in saved], [p.id])
        self.assertFalse(post_json(self.a, f"/api/posts/{p.id}/save").json()["isSaved"])


# ----------------------------------------------------------------------- comments
class CommentTests(ApiTestCase):
    def test_add_comment_appears_on_post(self):
        p = self.make_post()
        r = post_json(self.b, f"/api/posts/{p.id}/comments", {"content": "nice!"})
        self.assertEqual(r.status_code, 201)
        feed = self.a.get("/api/posts?author=alice").json()["results"][0]
        self.assertEqual(len(feed["comments"]), 1)
        self.assertEqual(feed["comments"][0]["user"]["username"], "bob")

    def test_empty_and_too_long_comments_rejected(self):
        p = self.make_post()
        self.assertEqual(post_json(self.b, f"/api/posts/{p.id}/comments", {"content": "   "}).status_code, 400)
        self.assertEqual(post_json(self.b, f"/api/posts/{p.id}/comments", {"content": "x" * 501}).status_code, 400)

    def test_comment_on_missing_post_404(self):
        self.assertEqual(post_json(self.b, "/api/posts/999999/comments", {"content": "hi"}).status_code, 404)

    def test_comment_notifies_author_but_not_self(self):
        p = self.make_post()
        post_json(self.b, f"/api/posts/{p.id}/comments", {"content": "hello"})
        post_json(self.a, f"/api/posts/{p.id}/comments", {"content": "my own"})
        kinds = list(Notification.objects.filter(recipient=self.alice).values_list("kind", flat=True))
        self.assertEqual(kinds, [Notification.COMMENT])


# --------------------------------------------------------------------------- likes
class LikeTests(ApiTestCase):
    def test_like_unlike_toggle_with_counts(self):
        p = self.make_post()
        r = post_json(self.b, f"/api/posts/{p.id}/like").json()
        self.assertEqual((r["isLiked"], r["likesCount"]), (True, 1))
        r = post_json(self.b, f"/api/posts/{p.id}/like").json()
        self.assertEqual((r["isLiked"], r["likesCount"]), (False, 0))

    def test_like_counts_across_users(self):
        p = self.make_post()
        post_json(self.a, f"/api/posts/{p.id}/like")
        r = post_json(self.b, f"/api/posts/{p.id}/like").json()
        self.assertEqual(r["likesCount"], 2)

    def test_like_notifies_once_and_not_self(self):
        p = self.make_post()
        post_json(self.b, f"/api/posts/{p.id}/like")
        post_json(self.b, f"/api/posts/{p.id}/like")  # unlike
        post_json(self.b, f"/api/posts/{p.id}/like")  # like again
        post_json(self.a, f"/api/posts/{p.id}/like")  # own post
        self.assertEqual(Notification.objects.filter(recipient=self.alice, kind=Notification.LIKE).count(), 1)

    def test_like_missing_post_404(self):
        self.assertEqual(post_json(self.a, "/api/posts/999999/like").status_code, 404)


# -------------------------------------------------------------------------- follow
class FollowTests(ApiTestCase):
    def test_follow_unfollow_toggle_and_counts(self):
        r = post_json(self.a, "/api/users/bob/follow").json()
        self.assertEqual((r["isFollowing"], r["followersCount"], r["followingCount"]), (True, 1, 1))
        self.assertEqual(self.b.get("/api/users/bob").json()["followersCount"], 1)
        r = post_json(self.a, "/api/users/bob/follow").json()
        self.assertEqual((r["isFollowing"], r["followersCount"]), (False, 0))

    def test_cannot_follow_self(self):
        self.assertEqual(post_json(self.a, "/api/users/alice/follow").status_code, 400)
        self.assertEqual(Follow.objects.count(), 0)

    def test_follow_unknown_user_404(self):
        self.assertEqual(post_json(self.a, "/api/users/nobody/follow").status_code, 404)

    def test_following_feed_only_shows_followed_and_self(self):
        carol = User.objects.create_user("carol", password=PASSWORD)
        mine, bobs, carols = self.make_post(), self.make_post(author=self.bob), self.make_post(author=carol)
        post_json(self.a, "/api/users/bob/follow")
        ids = {p["id"] for p in self.a.get("/api/posts?filter=following").json()["results"]}
        self.assertEqual(ids, {mine.id, bobs.id})
        self.assertNotIn(carols.id, ids)

    def test_follow_notifies_target(self):
        post_json(self.a, "/api/users/bob/follow")
        self.assertEqual(Notification.objects.filter(recipient=self.bob, kind=Notification.FOLLOW).count(), 1)


# -------------------------------------------------------------- DB-level constraints
class ConstraintTests(ApiTestCase):
    def test_database_blocks_duplicate_like_and_self_follow(self):
        from django.db import IntegrityError, transaction

        p = self.make_post()
        Like.objects.create(user=self.bob, post=p)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Like.objects.create(user=self.bob, post=p)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Follow.objects.create(follower=self.alice, following=self.alice)


# ------------------------------------------------------------------ stories (list + visibility)
class StoryListTests(ApiTestCase):
    def test_story_list_returns_all_active_stories_oldest_first(self):
        alice = self.alice
        Follow.objects.create(follower=self.bob, following=alice)

        first = Story.objects.create(user=alice, text="first")
        second = Story.objects.create(user=alice, text="second")
        other = Story.objects.create(user=self.bob, text="bob story")

        data = self.b.get("/api/stories").json()["results"]
        self.assertEqual([item["id"] for item in data], [first.id, second.id, other.id])

    def test_story_list_includes_my_own_stories(self):
        mine1 = Story.objects.create(user=self.alice, text="mine 1")
        mine2 = Story.objects.create(user=self.alice, text="mine 2")

        story_ids = [item["id"] for item in self.a.get("/api/stories").json()["results"]]
        self.assertIn(mine1.id, story_ids)
        self.assertIn(mine2.id, story_ids)

    def test_story_list_excludes_unfollowed_users(self):
        carol = User.objects.create_user("carol", password=PASSWORD, display_name="Carol")
        secret = Story.objects.create(user=carol, text="secret")

        story_ids = [item["id"] for item in self.a.get("/api/stories").json()["results"]]
        self.assertNotIn(secret.id, story_ids)

    def test_story_list_excludes_stories_older_than_24h(self):
        old = Story.objects.create(user=self.alice, text="old", created_at=timezone.now() - timedelta(hours=25))

        story_ids = [item["id"] for item in self.a.get("/api/stories").json()["results"]]
        self.assertNotIn(old.id, story_ids)


# ------------------------------------------------------------------ stories (likers)
class StoryLikersVisibilityTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.story = Story.objects.create(user=self.alice, text="hello")
        StoryLike.objects.create(user=self.bob, story=self.story)

    def test_author_can_see_likers(self):
        r = self.a.get(f"/api/stories/{self.story.id}/likes")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([u["username"] for u in r.json()["results"]], ["bob"])

    def test_follower_can_see_likers(self):
        Follow.objects.create(follower=self.bob, following=self.alice)
        self.assertEqual(self.b.get(f"/api/stories/{self.story.id}/likes").status_code, 200)

    def test_non_follower_cannot_see_likers(self):
        # bob liked the story but does not follow alice -> must be denied
        self.assertEqual(self.b.get(f"/api/stories/{self.story.id}/likes").status_code, 404)

    def test_stranger_cannot_see_likers(self):
        carol = User.objects.create_user("carol", password=PASSWORD)
        c = Client()
        c.force_login(carol)
        self.assertEqual(c.get(f"/api/stories/{self.story.id}/likes").status_code, 404)


class StoryActionsVisibilityTests(ApiTestCase):
    """Marking a story seen / liking it follows the same visibility rule as the stories feed."""

    def setUp(self):
        super().setUp()
        self.story = Story.objects.create(user=self.alice, text="hello")

    def test_non_follower_cannot_mark_seen_or_like(self):
        self.assertEqual(post_json(self.b, f"/api/stories/{self.story.id}/seen").status_code, 404)
        self.assertEqual(post_json(self.b, f"/api/stories/{self.story.id}/like").status_code, 404)
        self.assertEqual(StoryLike.objects.count(), 0)
        self.assertEqual(self.story.views.count(), 0)

    def test_follower_can_mark_seen_and_toggle_like(self):
        Follow.objects.create(follower=self.bob, following=self.alice)
        self.assertEqual(post_json(self.b, f"/api/stories/{self.story.id}/seen").status_code, 200)
        r = post_json(self.b, f"/api/stories/{self.story.id}/like").json()
        self.assertEqual((r["isLiked"], r["likesCount"]), (True, 1))
        r = post_json(self.b, f"/api/stories/{self.story.id}/like").json()
        self.assertEqual((r["isLiked"], r["likesCount"]), (False, 0))

    def test_author_can_act_on_own_story(self):
        self.assertEqual(post_json(self.a, f"/api/stories/{self.story.id}/seen").status_code, 200)
        self.assertEqual(post_json(self.a, f"/api/stories/{self.story.id}/like").status_code, 200)

    def test_unfollowing_removes_access(self):
        Follow.objects.create(follower=self.bob, following=self.alice)
        post_json(self.b, f"/api/stories/{self.story.id}/like")
        Follow.objects.all().delete()
        self.assertEqual(post_json(self.b, f"/api/stories/{self.story.id}/like").status_code, 404)
