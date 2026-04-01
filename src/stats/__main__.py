"""CLI entry point: ``python -m stats <analysis> [options]``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyses import ANALYSES
from .compare import compare
from .groups import GROUPS


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="stats",
        description="Set piece analysis for UCL 2025-26.",
    )
    parser.add_argument(
        "analysis",
        nargs="?",
        choices=[*ANALYSES.keys(), "all"],
        help="Analysis to run (or 'all').",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available analyses and exit.",
    )
    parser.add_argument(
        "--team",
        default="Barcelona",
        help="Focus team (default: Barcelona).",
    )
    parser.add_argument(
        "--compare",
        default="top16",
        choices=list(GROUPS.keys()),
        help="Comparison group (default: top16).",
    )
    parser.add_argument(
        "--per-team",
        action="store_true",
        help="Include full per-team results in output.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "data" / "statsbomb",
        help="Path to StatsBomb data directory or .zip.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file (.json) or directory (for 'all'). Default: stdout.",
    )

    args = parser.parse_args(argv)

    if args.list:
        print("Available analyses:")
        for name in ANALYSES:
            print(f"  {name}")
        return

    if not args.analysis:
        parser.print_help()
        sys.exit(1)

    group = GROUPS[args.compare]

    if args.analysis == "all":
        modules = list(ANALYSES.items())
    else:
        modules = [(args.analysis, ANALYSES[args.analysis])]

    results = {}
    for name, module in modules:
        print(f"Running {name}...", file=sys.stderr)
        result = compare(
            analysis_module=module,
            data_dir=args.data_dir,
            focus_team=args.team,
            group=group,
            per_team=args.per_team,
        )
        results[name] = result

    # Single analysis → output the result directly; 'all' → wrap in dict
    output = results if len(results) > 1 else next(iter(results.values()))
    payload = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
