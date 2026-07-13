"""Django project configuration."""
"""Malaysia Transit Live Django configuration package."""

from config.celery import app as celery_app

__all__ = ["celery_app"]
