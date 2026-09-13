"""Smoke tests: verify the repository imports cleanly and logging is functional."""

import json
import logging

from core.logging_setup import JsonFormatter, configure_logging, get_logger


def test_packages_import_cleanly() -> None:
    import core
    import recon
    import recon.subdomains
    import recon.dns
    import recon.network
    import recon.web
    import recon.historical
    import database
    import evidence
    import reports
    import intelligence
    import ai
    import correlation

    assert core.__version__ == "0.1.0"


def test_logger_emits_json_lines() -> None:
    import io

    configure_logging()

    stream = io.StringIO()

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            stream.write(self.format(record) + "\n")

    root = logging.getLogger()
    root.handlers = []
    handler = _Handler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    logger = get_logger("smoke")
    logger.info("hello %s", "argus", extra={"run_id": "r-1"})

    line = json.loads(stream.getvalue().strip())
    assert line["logger"] == "argus.smoke"
    assert line["message"] == "hello argus"
    assert line["run_id"] == "r-1"
    assert line["ts"].endswith("Z") or "+00:00" in line["ts"]