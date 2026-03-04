from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_REPORT_SCHEMA = "app.cli.graph_tools.validate_graphs.report"
_LEVEL_ERROR = "error"
_EXIT_OK = 0
_EXIT_FAIL = 1


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "CI gate for validate-graphs JSON report: fail only when there are errors "
            "(warnings do not block CI)."
        )
    )
    parser.add_argument(
        "report_json",
        type=Path,
        help="Path to JSON report produced by: python -m app.cli.graph_tools validate-graphs --all --json",
    )
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object at top-level, got: {type(data).__name__}")
    return data


def _count_errors(report: dict[str, Any]) -> int:
    issues = report.get("issues")
    if not isinstance(issues, list):
        raise TypeError("report['issues'] must be a list")

    errors = 0
    for item in issues:
        if not isinstance(item, dict):
            continue
        if item.get("level") == _LEVEL_ERROR:
            errors += 1
    return errors


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    report_path: Path = args.report_json

    report = _load_json(report_path)

    schema = report.get("schema")
    if schema != _REPORT_SCHEMA:
        raise ValueError(f"unexpected report schema: {schema!r} (expected {_REPORT_SCHEMA!r})")

    error_count = _count_errors(report)

    if error_count > 0:
        print(f"[FAIL] validate-graphs has errors: {error_count} (report={report_path.as_posix()})")
        return _EXIT_FAIL

    stats = report.get("stats")
    if isinstance(stats, dict):
        warnings = stats.get("issues_by_level", {}).get("warning")
        if isinstance(warnings, int) and warnings > 0:
            print(f"[OK] validate-graphs has 0 errors; warnings={warnings} (report={report_path.as_posix()})")
            return _EXIT_OK

    print(f"[OK] validate-graphs has 0 errors (report={report_path.as_posix()})")
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
