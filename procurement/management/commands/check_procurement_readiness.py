import json

from django.core.management.base import BaseCommand, CommandError

from procurement.events.health import procurement_readiness


class Command(BaseCommand):
    help = "Check database and opt-in RabbitMQ readiness without affecting Django startup."

    def handle(self, *args, **options):
        result = procurement_readiness()
        self.stdout.write(json.dumps(result))
        if not result["ready"]:
            raise CommandError("Procurement is not ready")
