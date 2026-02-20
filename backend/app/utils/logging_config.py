"""
Logging configuration for the application.
Integrates with uvicorn's existing log handlers so everything
appears in the same console output.
"""

import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """
    Configure application logging to integrate with uvicorn.

    - Re-uses uvicorn's existing handlers so format/color stay consistent.
    - Falls back to a basic StreamHandler if uvicorn hasn't initialised yet.
    - Sets the 'app' logger (and all child loggers) to INFO (or DEBUG in debug mode).
    """
    level = logging.DEBUG if debug else logging.INFO

    uvicorn_logger = logging.getLogger("uvicorn")
    handlers = uvicorn_logger.handlers

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s:     %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    if not handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(fmt)
        handlers = [handler]
    else:
        for h in handlers:
            h.setFormatter(fmt)

    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    app_logger.propagate = False

    for h in handlers:
        app_logger.addHandler(h)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "dspy"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
