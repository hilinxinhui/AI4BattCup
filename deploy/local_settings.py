from .base import *

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "minio", "django"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:8080", "http://127.0.0.1:8080"]
CSRF_ALLOWED_ORIGINS = CSRF_TRUSTED_ORIGINS
SITE_DOMAIN = "http://localhost:8080"

# Prefer the competition site's templates over upstream promotional pages.
TEMPLATES[0]["DIRS"].insert(0, "/app/site_templates")
