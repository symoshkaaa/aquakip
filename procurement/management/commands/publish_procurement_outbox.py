from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from procurement.events.publisher import publish_pending


class Command(BaseCommand):
    help = "Publish a bounded outbox batch with RabbitMQ broker confirmations."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        try:
            result = publish_pending(limit=options["limit"])
        except (ValueError, ImproperlyConfigured) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(f"Published: {result.published}; failed: {result.failed}")
        if result.failed:
            raise CommandError("Unconfirmed events remain pending for retry")
