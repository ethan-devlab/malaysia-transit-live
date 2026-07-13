"""Transit Django application configuration."""

from django.apps import AppConfig


class TransitConfig(AppConfig):
    """Register the transit domain with Django."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "transit"
