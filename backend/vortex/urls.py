from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse, HttpResponseNotFound
from django.urls import include, path, re_path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.static import serve
from django.conf.urls.static import static


@ensure_csrf_cookie
def index(request):
    """Serve the single-page frontend and make sure the CSRF cookie is set."""
    page = settings.FRONTEND_DIR / "index.html"
    if not page.exists():
        return HttpResponseNotFound("frontend/index.html not found")
    return HttpResponse(page.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("feed.urls")),
]

if settings.SERVE_FRONTEND:
    urlpatterns += [
        re_path(
            r"^(?P<path>(?:css|js|assets)/.+)$",
            serve,
            {"document_root": settings.FRONTEND_DIR},
        ),
        path("", index),
    ]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
