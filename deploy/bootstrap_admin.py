"""Run with manage.py shell; credentials come from the container environment."""
import os
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

User = get_user_model()
username = os.environ["DJANGO_SUPERUSER_USERNAME"]
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username=username,
        email=os.environ["DJANGO_SUPERUSER_EMAIL"],
        password=os.environ["DJANGO_SUPERUSER_PASSWORD"],
    )
    print("Administrator created.")
else:
    print("Administrator already exists; password preserved.")
Site.objects.update_or_create(id=1, defaults={"domain": "localhost:8080", "name": "AI4Batt Cup"})
