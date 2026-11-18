import json
import logging
import sys

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


def setup_logging(debug: bool = True) -> None:
    """Configures structured logging with JSON output for observability."""
    log_level = logging.DEBUG if debug else logging.INFO

    if HAS_STRUCTLOG:
        shared_processors: list = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
        ]

        if sys.stderr.isatty() and debug:
            processors = shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ]
        else:
            processors = shared_processors + [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ]

        structlog.configure(
            processors=processors,
            logger_factory=structlog.PrintLoggerFactory(),
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            cache_logger_on_first_use=True,
        )
    else:
        # Standard library logging fallback
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt='{"timestamp":"%(asctime)s", "level":"%(levelname)s", "logger":"%(name)s", "message":"%(message)s"}'
        )
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers = [handler]


class StandardLoggerAdapter:
    """Lightweight adapter mimicking structlog for standard logging fallback."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def info(self, event: str, **kwargs):
        self._logger.info(json.dumps({"event": event, **kwargs}))

    def debug(self, event: str, **kwargs):
        self._logger.debug(json.dumps({"event": event, **kwargs}))

    def warning(self, event: str, **kwargs):
        self._logger.warning(json.dumps({"event": event, **kwargs}))

    def error(self, event: str, **kwargs):
        self._logger.error(json.dumps({"event": event, **kwargs}))


def get_logger(name: str = "araa"):
    """Returns a contextual bound logger."""
    if HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return StandardLoggerAdapter(logging.getLogger(name))

