"""ARGUS command-line entry point (Milestone 1 Phase 0 no-op).

The doc-specified flow (``15_FIRST_MILESTONE.md``) starts at the CLI: intake of
target + scope, then scope validation. Later milestones wire real subcommands.
"""

from __future__ import annotations

import argparse
import sys

from core.logging_setup import configure_logging, get_logger


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = get_logger("cli")
    parser = argparse.ArgumentParser(
        prog="argus",
        description="Adaptive Reconnaissance & Graph-based Unified Security.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print version and exit",
    )
    args = parser.parse_args(argv)

    if args.version:
        from core import __version__

        print(f"argus {__version__}")
        return 0

    logger.info("argus bootstrap: no-op CLI invoked")
    print("argus: nothing to do yet (Milestone 1 Phase 0 bootstrap)")
    return 0


if __name__ == "__main__":
    sys.exit(main())