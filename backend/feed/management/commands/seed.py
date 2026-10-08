"""Populate the database with demo users, posts, stories and activity.

    python manage.py seed            # add demo data (idempotent for users)
    python manage.py seed --reset    # wipe demo content first

All demo accounts share the password given by --password (default: vortex123).
Log in as "jordanvale" to see the app the way the original mock did.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from feed.models import (
    Comment, Follow, Like, Notification, Post, SavedPost, Story, User,
)

AV = {
    "elena": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/avatar-elena-e1f853d3-1791273039905.webp",
    "marcus": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/avatar-marcus-ac0c01c2-1791273040261.webp",
    "sophia": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/avatar-sophia-8c5945e0-1791273039257.webp",
    "alex": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/avatar-alex-9e453c2e-1791273040506.webp"
}
IMG = {
    "cyberpunk": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/post-cyberpunk-d470319e-1791273039819.webp",
    "architecture": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/post-architecture-40c628ae-1791273040061.webp",
    "generative": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/post-generative-01c076b4-1791273040027.webp",
    "street": "https://dala-prod-public-storage.s3.eu-west-1.amazonaws.com/generated-images/b7b3c985-4305-4d48-82b2-3696d43380a4/post-street-0accfd1b-1791273040142.webp"
}

USERS = [
    dict(username="jordanvale", display_name="Jordan Vale", avatar_url=AV["elena"], cover_url=IMG["generative"],
         bio="Digital artist & night-owl photographer. Chasing neon, light and the quiet edges of the city. Building things that glow.",
         location="Neo Tokyo", website="vortex.studio", verified=True),
    dict(username="elenavance", display_name="Elena Vance", avatar_url=AV["elena"],
         bio="Portrait artist. Light is everything.", location="Berlin", verified=True),
    dict(username="marcuschen", display_name="Marcus Chen", avatar_url=AV["marcus"],
         bio="Generative art & creative code.", location="Singapore"),
    dict(username="sophiaray", display_name="Sophia Ray", avatar_url=AV["sophia"],
         bio="Street photographer. The city tells stories.", location="New York", verified=True),
    dict(username="alexrivera", display_name="Alex Rivera", avatar_url=AV["alex"],
         bio="Architecture & minimalism nerd.", location="Barcelona"),
]

POSTS = [
    ("elenavance", "cyberpunk", "Rain-slicked streets turned into a river of neon tonight. Shot this three blocks from my studio, the violet reflections were unreal.",
     ["cyberpunk", "night", "neon"], "Shibuya, Tokyo", 2),
    ("alexrivera", "architecture", "Concrete, shadow, and a single beam of light. Minimalism isn't empty, it's full of restraint.",
     ["architecture", "minimal"], "Barcelona", 5),
    ("marcuschen", "generative", "New generative series. Thousands of particles, one algorithm, zero repetition. Full code dropping this weekend.",
     ["generative", "creativecode", "art"], "Singapore", 8),
    ("sophiaray", "street", "Dusk walk. One figure, a pool of violet light, and the hum of the city. Street photography at its quietest.",
     ["street", "dusk", "urban"], "New York", 12),
]

COMMENTS = [
    (0, "marcuschen", "The color grade here is insane", 60),
    (0, "alexrivera", "Wish I was there shooting this!", 48),
    (1, "sophiaray", "That staircase though", 180),
    (2, "elenavance", "This is pure eye candy. Need a print!", 360),
    (3, "marcuschen", "The mood in this is unmatched.", 540),
]


class Command(BaseCommand):
    help = "Create demo data for Vortex."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo users (and their content) first.")
        parser.add_argument("--password", default="vortex123")

    @transaction.atomic
    def handle(self, *args, **opts):
        names = [u["username"] for u in USERS]
        if opts["reset"]:
            User.objects.filter(username__in=names).delete()

        users = {}
        for spec in USERS:
            spec = dict(spec)
            username = spec.pop("username")
            user, created = User.objects.get_or_create(username=username, defaults=spec)
            if created:
                user.set_password(opts["password"])
                user.save()
            users[username] = user

        if Post.objects.filter(author__username__in=names).exists():
            self.stdout.write(self.style.WARNING("Demo posts already exist - use --reset to recreate."))
            return

        now = timezone.now()
        me = users["jordanvale"]
        for other in ("marcuschen", "alexrivera"):
            Follow.objects.get_or_create(follower=me, following=users[other])
        Follow.objects.get_or_create(follower=users["elenavance"], following=me)
        Follow.objects.get_or_create(follower=users["marcuschen"], following=me)

        posts = []
        for author, img, caption, tags, loc, hours in POSTS:
            posts.append(Post.objects.create(
                author=users[author], image_url=IMG[img], caption=caption, tags=tags,
                location=loc, created_at=now - timedelta(hours=hours),
            ))

        for idx, who, text, mins in COMMENTS:
            Comment.objects.create(post=posts[idx], user=users[who], content=text, created_at=now - timedelta(minutes=mins))

        # a few likes / saves so counts and flags are non-zero
        for p in posts:
            for name in names:
                if name != p.author.username and (p.id + len(name)) % 2 == 0:
                    Like.objects.get_or_create(user=users[name], post=p)
        Like.objects.get_or_create(user=me, post=posts[1])
        SavedPost.objects.get_or_create(user=me, post=posts[1])

        for author, img, *_ in POSTS:
            Story.objects.create(user=users[author], image_url=IMG[img], created_at=now - timedelta(hours=1))

        Notification.objects.create(recipient=me, actor=users["elenavance"], kind="like", post=None, created_at=now - timedelta(minutes=5))
        Notification.objects.create(recipient=me, actor=users["marcuschen"], kind="follow", created_at=now - timedelta(minutes=22))
        Notification.objects.create(recipient=me, actor=users["sophiaray"], kind="comment", excerpt="Gorgeous!",
                                    unread=False, created_at=now - timedelta(hours=1))

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(users)} users. Log in as 'jordanvale' / '{opts['password']}'."))
