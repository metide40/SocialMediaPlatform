# Vortex – full stack

- **Frontend:** HTML + CSS + vanilla JavaScript (`frontend/`, no build step)
- **Backend:** Django + PostgreSQL JSON API (`backend/`)
- Django also serves the frontend, so everything runs on one origin (session cookies + CSRF just work).

## Quick start

```bash
# 1. PostgreSQL (skip if you already have one – then create a db/user matching .env.example)
docker compose up -d db

# 2. Python environment
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configuration (Django does not read .env by itself – export the variables)
cp .env.example .env
set -a; source .env; set +a                             # Windows: set each variable manually

# 4. Create tables (custom user model => makemigrations first, and commit the generated files)
python manage.py makemigrations feed
python manage.py migrate

# 5. Demo data + admin user
python manage.py seed                                   # users: jordanvale, elenavance, ... password: vortex123
python manage.py createsuperuser

# 6. Run
python manage.py runserver
```

Open <http://localhost:8000> and log in as `jordanvale` / `vortex123` (or sign up).
Admin: <http://localhost:8000/admin/>.

## API (all JSON, session-cookie auth, `X-CSRFToken` header on POSTs)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` `{username,password,displayName}` | create account + log in |
| POST | `/api/auth/login` `{username,password}` | log in |
| POST | `/api/auth/logout` | log out |
| GET | `/api/me` | current user (401 if logged out) |
| POST/PATCH | `/api/me` | update profile (`displayName`, `bio`, `location`, `website`, `avatarUrl`, `coverUrl` or multipart `avatar`/`cover` files) |
| GET | `/api/users/<username>` | profile |
| POST | `/api/users/<username>/follow` | toggle follow (returns `isFollowing`, `followersCount`, `followingCount`) |
| GET | `/api/posts?filter=for-you\|following\|explore\|saved&author=&q=&limit=&offset=` | feed |
| POST | `/api/posts` | create post — JSON `{imageUrl,caption,location,tags}` **or** multipart with `image` file |
| POST | `/api/posts/<id>/like` · `/save` | toggle like / save |
| POST | `/api/posts/<id>/comments` `{content}` | add comment |
| POST | `/api/posts/<id>/delete` | delete own post |
| GET | `/api/stories` | stories (last 24h, you + people you follow) |
| POST | `/api/stories` | create story — JSON `{imageUrl}` or multipart `image` file |
| POST | `/api/stories/<id>/seen` | mark story seen |
| GET | `/api/notifications` · POST `/api/notifications/read` | notifications |

## Data model
`User` (custom, extends `AbstractUser`) · `Follow` · `Post` · `Like` · `SavedPost` · `Comment` · `Story` · `StoryView` · `Notification`.
Uniqueness (one like/save/follow per pair, no self-follow) is enforced by database constraints.

## Production notes
- Set `DJANGO_DEBUG=0`, a real `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Run with `gunicorn vortex.wsgi`; serve `frontend/` from nginx (or keep `DJANGO_SERVE_FRONTEND=1` for small deployments).
- Image uploads are stored under `backend/media/` and served at `/media/`.
- Not included yet: rate limiting on login, tests.
