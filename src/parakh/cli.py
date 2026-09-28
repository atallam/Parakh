"""Command line: `parakh --help`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parakh import __version__
from parakh.config import env_file, get_settings
from parakh.observability.logging import configure_logging

SECRET_SUFFIXES = ("_key", "_token", "_password", "_secret", "_id")


def _doctor() -> int:
    """Report configuration without calling any external service or printing secrets."""
    settings = get_settings()
    path = env_file()
    print(f"parakh {__version__} · env={settings.app_env} · model={settings.llm_model}")
    print(f".env file: {path if path else 'none found (using environment variables only)'}")
    for field_name, info in type(settings).model_fields.items():
        if "SecretStr" in str(info.annotation) or field_name.endswith(SECRET_SUFFIXES):
            value = getattr(settings, field_name)
            print(f"  {field_name.upper():32} {'set' if value else 'missing'}")
    return 0


def _summarize(path: str) -> int:
    from parakh.orchestration.graph import run_pipeline

    result = run_pipeline(Path(path).read_text(encoding="utf-8"))
    summary = result.summary
    if summary is None:
        print("Summary unavailable: the LLM could not be reached. Try again later.")
        return 2
    print(summary.model_dump_json(indent=2))
    if result.needs_review:
        print(f"Flagged for human review: {result.review_reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="parakh",
        description="Personal NSE stock-analysis framework with value and momentum lenses and Telegram alerts",
    )
    parser.add_argument("--version", action="version", version=f"parakh {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="check configuration (no external calls)")
    p_sum = sub.add_parser("summarize", help="example agent: summarise a text file")
    p_sum.add_argument("path")
    args = parser.parse_args(argv)

    configure_logging()
    if args.command == "doctor":
        return _doctor()
    if args.command == "summarize":
        return _summarize(args.path)
    parser.print_help(sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
