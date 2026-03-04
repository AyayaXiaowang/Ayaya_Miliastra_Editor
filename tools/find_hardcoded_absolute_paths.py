from __future__ import annotations

import argparse
import ast
import dataclasses
import os
import re
import tokenize
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Iterable, Iterator, Sequence

REPO_ROOT_PARENT_LEVELS = 1
EXIT_CODE_OK = 0
EXIT_CODE_FOUND = 2

EXCLUDE_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
    }
)

TARGET_SUFFIX_LOWER = ".py"

OUTPUT_LINE_MAX_CHARS = 240
EXCLUDED_REL_FILES = frozenset(
    {
        # Avoid self-noise in repos that vendor this tool in multiple places.
        "tools/find_hardcoded_absolute_paths.py",
    }
)


def _repo_root_from_this_file() -> Path:
    # tools/*.py -> repo_root
    return Path(__file__).resolve().parents[REPO_ROOT_PARENT_LEVELS]


def _to_posix_rel_path(repo_root: Path, abs_path: Path) -> str:
    return abs_path.resolve().relative_to(repo_root.resolve()).as_posix()


def _iter_candidate_files(repo_root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES]
        for name in filenames:
            p = Path(dirpath) / name
            suffix_lower = p.suffix.lower()
            if suffix_lower == TARGET_SUFFIX_LOWER:
                yield p


def _read_text_strict(path: Path) -> str:
    if path.suffix.lower() == ".py":
        with tokenize.open(str(path)) as f:
            return f.read()
    return path.read_text(encoding="utf-8", errors="strict")


_WIN_DRIVE_ABS_RE = re.compile(r"(?i)(?P<path>\b[a-z]:[\\/][^ \t\r\n\"'<>|]+)")

ABS_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("win_drive", _WIN_DRIVE_ABS_RE),
)


@dataclass(frozen=True, slots=True)
class Match:
    kind: str
    rel_file: str
    lineno: int
    abs_path_text: str
    line_preview: str

    def to_line(self) -> str:
        return f"ABS_PATH:{self.kind}:{self.rel_file}:{self.lineno}:{self.abs_path_text}\t{self.line_preview}"


@dataclass(frozen=True, slots=True)
class DecodeError:
    rel_file: str
    error: str

    def to_line(self) -> str:
        return f"DECODE_ERROR:{self.rel_file}:{self.error}"


def _trim_line_for_output(line: str) -> str:
    raw = line.rstrip("\r\n")
    if len(raw) <= OUTPUT_LINE_MAX_CHARS:
        return raw
    return raw[:OUTPUT_LINE_MAX_CHARS] + "<...truncated...>"


def _scan_text_for_absolute_paths(*, rel_file: str, text: str) -> list[Match]:
    out: list[Match] = []
    lines = text.splitlines()
    tokens = tokenize.generate_tokens(StringIO(text).readline)
    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        lineno = int(tok.start[0])
        token_text = str(tok.string)

        # Prefer scanning the evaluated string value (reduces false positives from regex syntax).
        # For f-strings (and other non-literal expressions), literal_eval will fail; then scan raw token text.
        scan_targets: list[str] = []
        try:
            v = ast.literal_eval(token_text)
        except Exception:
            scan_targets.append(token_text)
        else:
            if isinstance(v, str):
                scan_targets.append(v)
            else:
                scan_targets.append(token_text)

        line_preview = _trim_line_for_output(lines[lineno - 1] if 0 < lineno <= len(lines) else "")
        for kind, pattern in ABS_PATH_PATTERNS:
            for target in scan_targets:
                for m in pattern.finditer(target):
                    path_text = str(m.group("path"))
                    out.append(
                        Match(
                            kind=kind,
                            rel_file=rel_file,
                            lineno=lineno,
                            abs_path_text=path_text,
                            line_preview=line_preview,
                        )
                    )
    return out


def scan_repo_for_hardcoded_absolute_paths(*, repo_root: Path) -> tuple[list[Match], list[DecodeError], int]:
    matches: list[Match] = []
    decode_errors: list[DecodeError] = []
    scanned_files = 0

    for abs_path in _iter_candidate_files(repo_root):
        rel_file = _to_posix_rel_path(repo_root, abs_path)
        if rel_file in EXCLUDED_REL_FILES:
            continue
        try:
            text = _read_text_strict(abs_path)
        except Exception as e:  # noqa: BLE001 - surface failures as explicit records
            decode_errors.append(DecodeError(rel_file=rel_file, error=repr(e)))
            continue
        scanned_files += 1
        matches.extend(_scan_text_for_absolute_paths(rel_file=rel_file, text=text))

    matches.sort(key=lambda x: (x.rel_file, x.lineno, x.kind, x.abs_path_text))
    decode_errors.sort(key=lambda x: x.rel_file)
    return matches, decode_errors, scanned_files


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scan repo .py files for hardcoded absolute paths (Windows drive / UNC).")
    p.add_argument(
        "--repo-root",
        type=str,
        default="",
        help="仓库根目录（默认：脚本推断 tools/..）",
    )
    return p.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    import sys

    args = _parse_args(list(argv or sys.argv[1:]))

    default_root = _repo_root_from_this_file()
    repo_root = Path(str(args.repo_root or "")).expanduser()
    repo_root = repo_root if str(args.repo_root or "").strip() else default_root
    repo_root = repo_root.resolve()

    if not repo_root.is_dir():
        raise FileNotFoundError(f"repo_root not found: {repo_root}")

    matches, decode_errors, scanned_files = scan_repo_for_hardcoded_absolute_paths(repo_root=repo_root)

    print("[OK] scan hardcoded absolute paths")
    print(f"- repo_root: {repo_root}")
    print(f"- scanned_files: {scanned_files}")
    print(f"- matches: {len(matches)}")
    print(f"- decode_errors: {len(decode_errors)}")

    if matches:
        print("- match_lines:")
        for m in matches:
            print(f"  - {m.to_line()}")

    if decode_errors:
        print("- decode_error_lines:")
        for e in decode_errors:
            print(f"  - {e.to_line()}")

    return EXIT_CODE_OK if not matches else EXIT_CODE_FOUND


if __name__ == "__main__":
    raise SystemExit(main())

