from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Callable, Sequence

_PROGRESS_RE = re.compile(r"^\s*\[(\d+)\s*/\s*(\d+)\]\s*(.*?)\s*$")
_PYTHON_EXE_NAME = "python.exe"
_PYTHONW_EXE_NAME = "pythonw.exe"


@dataclass(frozen=True, slots=True)
class CliRunResult:
    exit_code: int
    stderr_tail: list[str]


def _select_cli_python_executable() -> str:
    """选择用于子进程 CLI 的 Python 可执行文件并尽量复用当前解释器以避免空 stderr 的静默失败。"""
    exe = Path(sys.executable).resolve()
    exe_name_cf = exe.name.casefold()

    if exe_name_cf in {_PYTHON_EXE_NAME, _PYTHONW_EXE_NAME}:
        return str(exe)

    # 运行在宿主程序 exe（或其它非 python.exe 解释器）下时，不能直接用 sys.executable 启动子进程。
    candidates: list[Path] = []
    candidates.append(exe.with_name(_PYTHON_EXE_NAME))
    candidates.append((Path(sys.base_prefix) / _PYTHON_EXE_NAME).resolve())
    candidates.append((Path(sys.prefix) / _PYTHON_EXE_NAME).resolve())

    for c in candidates:
        if c.is_file():
            return str(c)

    found = which(_PYTHON_EXE_NAME) or which("python")
    if found:
        return str(Path(found).resolve())

    raise RuntimeError(
        "\n".join(
            [
                "无法找到 python.exe 来运行 ugc_file_tools 子进程。",
                f"当前 sys.executable={str(exe)}（宿主 exe 可能无法正确执行 -X/-m 脚本，从而子进程失败且 stderr 为空）。",
                f"已尝试候选：{[str(x) for x in candidates]!r}",
                f"PATH which('python'): {str(found) if found else '(not found)'}",
            ]
        )
    )


def build_run_ugc_file_tools_command(*, workspace_root: Path, argv: Sequence[str]) -> list[str]:
    """构建运行 ugc_file_tools 的子进程命令行。"""
    script_path = (Path(workspace_root).resolve() / "private_extensions" / "run_ugc_file_tools.py").resolve()
    if not script_path.is_file():
        raise FileNotFoundError(str(script_path))
    return [_select_cli_python_executable(), "-X", "utf8", str(script_path), *[str(x) for x in argv]]


def parse_progress_from_stderr_line(line: str) -> tuple[int, int, str] | None:
    """从 stderr 行解析进度格式 `[i/total] label`。"""
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
    """运行子进程并解析输出流中的进度行，同时保留输出尾部用于错误提示。"""
    tail = deque(maxlen=max(1, int(stderr_tail_max_lines)))

    creationflags = 0
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)

    proc = subprocess.Popen(
        list(command),
        cwd=str(Path(cwd).resolve()),
        # 合并 stdout+stderr：
        # - 一些环境下 Python/启动器错误信息会输出到 stdout（例如 PATH 里命中 Windows Store stub），
        #   若 stdout=DEVNULL 会出现“exit_code!=0 但 stderr_tail 为空”，难以定位根因。
        # - progress 行仍以 `[i/total] label` 解析（输出流合并不影响解析）。
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    out = proc.stdout
    if out is None:
        return CliRunResult(exit_code=int(proc.wait()), stderr_tail=[])

    for raw_line in out:
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

