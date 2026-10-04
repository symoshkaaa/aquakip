from django.conf import settings
from django.db import connection

from procurement.events.rabbitmq import connect_rabbitmq


def procurement_readiness():
    result = {"ready": True, "database": {"reachable": False}, "rabbitmq": {"enabled": bool(settings.RABBITMQ_URL)}}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result["database"]["reachable"] = cursor.fetchone() == (1,)
    except Exception as error:
        result["database"]["error"] = type(error).__name__
    result["ready"] = result["database"]["reachable"]
    if settings.RABBITMQ_URL:
        broker = None
        try:
            broker = connect_rabbitmq()
            broker.channel()
            result["rabbitmq"]["reachable"] = True
        except Exception as error:
            result["rabbitmq"].update(reachable=False, error=type(error).__name__)
            result["ready"] = False
        finally:
            if broker is not None and broker.is_open:
                try:
                    broker.close()
                except Exception:
                    pass
    return result
