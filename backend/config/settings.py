"""Secure Django settings for Malaysia Transit Live."""

import os
import sys
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, unquote, urlparse

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR: Final = Path(__file__).resolve().parent.parent
_IS_TESTING: Final = "pytest" in sys.modules
_TEST_SECRET_KEY: Final = "test-only-secret-key-not-for-production"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if SECRET_KEY is None:
    if _IS_TESTING:
        SECRET_KEY = _TEST_SECRET_KEY
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set outside tests")

_DEBUG_DEFAULT: Final = "true" if _IS_TESTING else "false"
DEBUG: Final = os.environ.get("DJANGO_DEBUG", _DEBUG_DEFAULT).lower() == "true"
_DEFAULT_ALLOWED_HOSTS: Final = (
    "localhost,127.0.0.1,testserver" if _IS_TESTING else "localhost,127.0.0.1"
)
ALLOWED_HOSTS: Final = [
    *os.environ.get("DJANGO_ALLOWED_HOSTS", _DEFAULT_ALLOWED_HOSTS).split(","),
    "healthcheck.railway.app",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "transit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "transit.http.origin.WorkerOriginVerificationMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


def _database_configuration() -> dict[str, object]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }

    parsed_url = urlparse(database_url)
    if parsed_url.scheme not in {"postgres", "postgresql"}:
        message = "DATABASE_URL must use the postgres or postgresql scheme."
        raise ImproperlyConfigured(message)
    database_name = unquote(parsed_url.path.removeprefix("/"))
    if not database_name:
        message = "DATABASE_URL must include a database name."
        raise ImproperlyConfigured(message)

    query = parse_qs(parsed_url.query)
    options: dict[str, str] = {}
    sslmode = query.get("sslmode", [""])[0]
    if sslmode:
        options["sslmode"] = sslmode
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed_url.username or ""),
        "PASSWORD": unquote(parsed_url.password or ""),
        "HOST": parsed_url.hostname or "",
        "PORT": str(parsed_url.port or 5432),
        "CONN_HEALTH_CHECKS": True,
        "CONN_MAX_AGE": 60,
        "OPTIONS": options,
    }


DATABASES = {"default": _database_configuration()}

LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Kuala_Lumpur"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
WORKER_ORIGIN_SECRET = os.environ.get("WORKER_ORIGIN_SECRET", "")

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TIMEZONE = "Asia/Kuala_Lumpur"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 60
CELERY_BEAT_SCHEDULE = {
    "refresh-static-gtfs-daily": {
        "task": "transit.refresh_static_gtfs",
        "schedule": crontab(hour=4, minute=0),
    },
    "poll-realtime-vehicle-positions": {
        "task": "transit.poll_realtime_vehicle_positions",
        "schedule": crontab(minute="*"),
    },
}
