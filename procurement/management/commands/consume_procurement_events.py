import signal
import threading

from django.core.management.base import BaseCommand, CommandError

from procurement.events.transport import ProcurementConsumer


class Command(BaseCommand):
    help = "Consume Procurement subscriptions with manual ACK and bounded retry/DLQ."

    def add_arguments(self, parser):
        parser.add_argument("--max-messages", type=int, default=None, help="Optional bounded delivery count.")

    def handle(self, *args, **options):
        limit = options["max_messages"]
        if limit is not None and limit < 1:
            raise CommandError("--max-messages must be positive")
        stop = threading.Event()
        previous = {}
        if threading.current_thread() is threading.main_thread():
            for name in (signal.SIGINT, signal.SIGTERM):
                previous[name] = signal.signal(name, lambda signum, frame: stop.set())
        try:
            count = ProcurementConsumer().run(stop_event=stop, max_messages=limit)
        except Exception as error:
            raise CommandError(f"Consumer failed: {type(error).__name__}") from None
        finally:
            for name, handler in previous.items():
                signal.signal(name, handler)
        self.stdout.write(f"Consumer stopped after {count} deliveries")
