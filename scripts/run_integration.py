"""Opt-in real integration suites; --docker owns and removes only its isolated stack."""

import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from urllib.parse import quote
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", action="store_true", help="Start an ephemeral local PostgreSQL/RabbitMQ stack.")
    options = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    environment = os.environ.copy()
    compose = None
    if options.docker:
        environment.update(
            POSTGRES_DB="procurement_db", POSTGRES_USER="procurement",
            POSTGRES_PASSWORD=secrets.token_urlsafe(24),
            RABBITMQ_USER="procurement", RABBITMQ_PASSWORD=secrets.token_urlsafe(24),
            POSTGRES_HOST="127.0.0.1",
        )
        for name in ("POSTGRES_PORT", "RABBITMQ_PORT", "RABBITMQ_MANAGEMENT_PORT"):
            if not environment.get(name):
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 0))
                    environment[name] = str(probe.getsockname()[1])
        environment["RABBITMQ_URL"] = (
            f"amqp://procurement:{quote(environment['RABBITMQ_PASSWORD'], safe='')}"
            f"@127.0.0.1:{environment['RABBITMQ_PORT']}/%2F"
        )
        compose = ["docker", "compose", "-p", f"aquakip-it-{uuid4().hex[:12]}", "-f", "docker-compose.integration.yml"]
    elif not all(environment.get(name) for name in ("POSTGRES_PASSWORD", "RABBITMQ_URL")):
        parser.error("Supply POSTGRES_PASSWORD and RABBITMQ_URL, or use --docker")

    def run(command):
        subprocess.run(command, cwd=root, env=environment, check=True)

    try:
        if compose:
            run(compose + ["up", "-d", "--wait", "--wait-timeout", "180"])
        common = [sys.executable, "manage.py", "test", "--settings=procurement_service.settings_integration", "--noinput"]
        run(common + ["procurement.tests", "integration_tests.postgres_suite"])
        run(common + ["integration_tests.rabbitmq_suite"])
    finally:
        if compose:
            subprocess.run(compose + ["down", "--volumes"], cwd=root, env=environment, check=False)


if __name__ == "__main__":
    main()
