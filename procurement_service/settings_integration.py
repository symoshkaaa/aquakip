import os

from django.core.exceptions import ImproperlyConfigured

from procurement_service.settings import *  # noqa: F403


if not os.environ.get("POSTGRES_PASSWORD"):
    raise ImproperlyConfigured("POSTGRES_PASSWORD must be supplied for integration tests")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "procurement_db"),
        "USER": os.environ.get("POSTGRES_USER", "procurement"),
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    },
}
