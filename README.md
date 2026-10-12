# Vortex

A social feed built with Django and vanilla JavaScript. It has posts, likes, comments, follows, 24-hour stories, notifications, profiles, and a light and dark theme.

- **Frontend:** HTML, CSS and JavaScript in `frontend/` (no build step)
- **Backend:** Django + PostgreSQL JSON API in `backend/`
- Django serves the frontend too, so everything runs on one origin.

## Features

- Sign up and log in
- Feed with For You, Following and Explore, plus search
- Posts with photo upload or image URL, caption, location and tags
- Likes, saves and comments
- Stories: several per user, visible for 24 hours to you and the people you follow, with likes and a list of who liked
- Profiles with avatar upload, bio, follower counts, and Feed / Media / Saved / Liked tabs
- Follow and unfollow, with notifications
- Light and dark theme, responsive layout

## Quick start

You need Python 3.10+ and PostgreSQL (Docker is the easiest way to get it).

```bash
docker compose up -d db                  # PostgreSQL

cd backend
python -m venv .venv
source .venv/bin/activate                # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

export DJANGO_DEBUG=1                    # Windows PowerShell: $env:DJANGO_DEBUG = "1"
python manage.py migrate
python manage.py seed                    # demo data (optional)
python manage.py runserver
```

Open <http://localhost:8000> and log in as `jordanvale` / `vortex123`, or sign up.
To use the admin site at `/admin/`, first run `python manage.py createsuperuser`.

`seed --reset` recreates the demo data. The demo images are hosted on a third-party server and may stop loading.

## Tests

```bash
cd backend
python manage.py test
```

PostgreSQL must be running. The tests cover auth, profiles, posts, comments, likes, follows, notifications and the story rules.

## Configuration

Set these as environment variables (Django does not read `.env` files; see `backend/.env.example`).

| Variable                            | Default               | Purpose                        |
| ----------------------------------- | --------------------- | ------------------------------ |
| `DJANGO_DEBUG`                      | `0`                   | `1` for development            |
| `DJANGO_SECRET_KEY`                 | none                  | Required when debug is off     |
| `DJANGO_ALLOWED_HOSTS`              | `localhost,127.0.0.1` | Allowed host names             |
| `DJANGO_CSRF_TRUSTED_ORIGINS`       | empty                 | e.g. `https://your-domain.com` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | `vortex`              | Database login                 |
| `DB_HOST`, `DB_PORT`                | `localhost`, `5432`   | Database location              |

## API

JSON, session-cookie auth, `X-CSRFToken` header on non-GET requests.

| Area          | Endpoints                                                                                                                                                                                     |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Auth          | `POST /api/auth/register`, `/login`, `/logout`                                                                                                                                                |
| Profile       | `GET` / `PATCH` / `POST /api/me`, `GET /api/users/<username>`, `POST /api/users/<username>/follow`                                                                                            |
| Posts         | `GET` / `POST /api/posts` (filters: `for-you`, `following`, `explore`, `saved`, `liked`; also `author`, `q`, `limit`, `offset`), `POST /api/posts/<id>/like`, `/save`, `/comments`, `/delete` |
| Stories       | `GET` / `POST /api/stories`, `POST /api/stories/<id>/seen`, `/like`, `GET /api/stories/<id>/likes`                                                                                            |
| Notifications | `GET /api/notifications`, `POST /api/notifications/read`                                                                                                                                      |

Stories are visible only to their author and the author's followers, and expire after 24 hours.

## Production notes

- Set `DJANGO_DEBUG=0`, a real `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Run with `gunicorn vortex.wsgi` from `backend/`.
- Django serves uploads (`/media/`) and admin static files only when `DJANGO_DEBUG=1`. In production, serve `backend/media/` and the output of `collectstatic` with nginx or similar.

## Known limitations

- No rate limiting on login.
- The story "Reply to..." box is a placeholder, not a working input.
- The post menu's "Report" only shows a message, and "Copy link" copies the page address, not the post's.



