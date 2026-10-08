from django.urls import path

from . import views

urlpatterns = [
    path("auth/register", views.register),
    path("auth/login", views.login_view),
    path("auth/logout", views.logout_view),
    path("me", views.me),
    path("users/<str:username>", views.user_detail),
    path("users/<str:username>/follow", views.toggle_follow),
    path("posts", views.posts),
    path("posts/<int:post_id>/like", views.toggle_like),
    path("posts/<int:post_id>/save", views.toggle_save),
    path("posts/<int:post_id>/comments", views.add_comment),
    path("posts/<int:post_id>/delete", views.delete_post),
    path("stories", views.stories),
    path("stories/<int:story_id>/seen", views.story_seen),
    path("stories/<int:story_id>/like", views.toggle_story_like),
    path("stories/<int:story_id>/likes", views.story_likes),
    path("notifications", views.notifications),
    path("notifications/read", views.notifications_read),
]
