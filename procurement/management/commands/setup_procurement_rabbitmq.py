from django.core.management.base import BaseCommand, CommandError

from procurement.events.rabbitmq import setup_topology


class Command(BaseCommand):
    help = "Declare the durable Procurement RabbitMQ topology (idempotent)."

    def handle(self, *args, **options):
        try:
            setup_topology()
        except Exception as error:
            raise CommandError(f"Topology setup failed: {type(error).__name__}") from None
        self.stdout.write(self.style.SUCCESS("Procurement RabbitMQ topology ready"))
