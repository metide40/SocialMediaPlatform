from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("feed", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="story",
            name="text",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AlterField(
            model_name="story",
            name="image_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.CreateModel(
            name="StoryLike",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("story", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="likes", to="feed.story")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="story_likes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("user", "story"), name="unique_story_like"),
                ],
            },
        ),
    ]
