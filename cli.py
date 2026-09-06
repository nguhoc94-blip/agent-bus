"""Command-line entry for file_router_bot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import ConfigError, load_config
from app.watcher import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file_router_bot",
        description="Local deterministic file router (project/pod/role) — v1.1",
    )
    parser.add_argument("--config", required=True, type=Path,
                        help="Path to config.json (see config.example.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not move files; log planned actions only")
    parser.add_argument("--once", action="store_true",
                        help="Scan existing files once and exit (no live watcher)")
    parser.add_argument("--no-scan-existing", action="store_true",
                        help="Skip scanning files already present at startup")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"[CONFIG-ERROR] {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        config.dry_run = True

    return run(
        config,
        once=args.once,
        scan_existing=not args.no_scan_existing,
    )


if __name__ == "__main__":
    sys.exit(main())
