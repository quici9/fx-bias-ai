"""
File I/O utilities for FX Bias AI pipeline.

Provides atomic write operations and standardized exit codes
for all pipeline scripts.

Reference: System Design Section 5.1
"""

import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Standardized exit codes for all pipeline scripts
EXIT_SUCCESS = 0
EXIT_PARTIAL = 1  # Has data but incomplete — warning, not fail
EXIT_FAILED = 2   # No usable data — fail the job


def write_output(data: dict, path: str) -> None:
    """
    Atomic write — write to temp file first, then rename.
    Prevents data corruption if the process is killed mid-write.

    Args:
        data: Dictionary to serialize as JSON
        path: Target file path

    Raises:
        OSError: If file operations fail
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    tmp_path = path + ".tmp"

    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        os.rename(tmp_path, path)
        logger.info("Output written: %s", path)

    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def setup_logging(name: str) -> logging.Logger:
    """
    Configure standardized logging for pipeline scripts.
    Format is parseable by GitHub Actions log grouping.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
        stream=sys.stderr,
    )
    return logging.getLogger(name)
