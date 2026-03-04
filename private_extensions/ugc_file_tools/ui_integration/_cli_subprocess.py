from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

_PROGRESS_RE = re.compile(r"^\s*\[(\d+)\s*/\s*(\d+)\]\s*(.*?)\s*$")


@dataclass(frozen=True, slots=True)
class CliRunResult:
    exit_code: int
    stderr_tail: list[str]


def build_run_ugc_file_tools_command(*, workspace_root: Path, argv: Sequence[str]) -> list[str]:
    script_path = (Path(workspace_root).resolve() / "private_extensions" / "run_ugc_file_tools.py").resolve()
    if not script_path.is_file():
        raise FileNotFoundError(str(script_path))
    return [sys.executable, "-X", "utf8", str(script_path), *[str(x) for x in argv]]


def parse_progress_from_stderr_line(line: str) -> tuple[int, int, str] | None:
    m = _PROGRESS_RE.match(str(line or ""))
    if m is None:
        return None
    current = int(m.group(1))
    total = int(m.group(2))
    label = str(m.group(3) or "").strip()
    return int(current), int(total), str(label)


def run_cli_with_progress(
    *,
    command: Sequence[str],
    cwd: Path,
    on_progress: Callable[[int, int, str], None] | None = None,
    on_log_line: Callable[[str], None] | None = None,
    stderr_tail_max_lines: int = 200,
) -> CliRunResult:
    tail = deque(maxlen=max(1, int(stderr_tail_max_lines)))

    creationflags = 0
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)

    proc = subprocess.Popen(
        list(command),
        cwd=str(Path(cwd).resolve()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    stderr = proc.stderr
    if stderr is None:
        return CliRunResult(exit_code=int(proc.wait()), stderr_tail=[])

    for raw_line in stderr:
        line = str(raw_line).rstrip("\n")
        if line:
            tail.append(line)
        if callable(on_log_line):
            on_log_line(line)
        progress = parse_progress_from_stderr_line(line)
        if progress is not None and callable(on_progress):
            current, total, label = progress
            on_progress(int(current), int(total), str(label))

    return CliRunResult(exit_code=int(proc.wait()), stderr_tail=list(tail))

