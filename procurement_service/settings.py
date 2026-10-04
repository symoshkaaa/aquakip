import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-only-procurement-service-secret"
DEBUG = True
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "procurement",
]

MIDDLEWARE = ["procurement.events.context.CorrelationIdMiddleware"]

ROOT_URLCONF = "procurement_service.urls"
WSGI_APPLICATION = "procurement_service.wsgi.application"
ASGI_APPLICATION = "procurement_service.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
RABBITMQ_EXCHANGE_DOMAIN = os.environ.get("RABBITMQ_EXCHANGE_DOMAIN", "domain.events")
RABBITMQ_EXCHANGE_DEAD = os.environ.get("RABBITMQ_EXCHANGE_DEAD", "dead.letter")
RABBITMQ_PROCUREMENT_QUEUE = os.environ.get("RABBITMQ_PROCUREMENT_QUEUE", "procurement.events")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"events": {"()": "procurement.events.logging.EventJSONFormatter"}},
    "handlers": {
        "events": {"class": "logging.StreamHandler", "formatter": "events"},
        "logging_null": {"class": "logging.NullHandler"},
    },
    "loggers": {
        "procurement.events": {"handlers": ["events"], "level": "INFO", "propagate": False},
        # Pika may include connection URLs in its own diagnostics.
        "pika": {"handlers": ["logging_null"], "propagate": False},
    },
}
