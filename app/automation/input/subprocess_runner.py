# -*- coding: utf-8 -*-
"""
子进程隔离调用工具

用途：在需要隔离 DPI/STDOUT 等全局副作用时，从当前 GUI 进程外部
调用独立的 `capture_beyondeditor.py`，通过文件/图片等方式回传结果。

说明：该模块不做异常吞噬，缺少脚本或执行失败会直接抛错或返回非零码。
"""

from __future__ import annotations

import sys
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass(frozen=True)
class ProcessResult:
    """通用子进程结果。"""

    exit_code: int
    stdout: str | None
    stderr: str | None


def run_process(
    args: Sequence[str],
    working_directory: Optional[Path | str] = None,
    capture_output: bool = True,
    text_mode: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> ProcessResult:
    """以统一方式运行外部进程，返回退出码与可选输出。"""
    completed = subprocess.run(
        list(args),
        cwd=str(working_directory) if working_directory is not None else None,
        capture_output=capture_output,
        text=text_mode,
        encoding=encoding if text_mode else None,
        errors=errors if text_mode else None,
    )
    return ProcessResult(
        exit_code=int(completed.returncode),
        stdout=str(completed.stdout) if capture_output and text_mode else None,
        stderr=str(completed.stderr) if capture_output and text_mode else None,
    )


def spawn_process(
    args: Sequence[str],
    *,
    working_directory: Optional[Path | str] = None,
    env: dict[str, str] | None = None,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    text_mode: bool = False,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> subprocess.Popen:
    """启动子进程（适用于常驻服务/后台工具）。

    说明：
    - 不做异常吞没；启动失败会直接抛错；
    - 若需要捕获输出，建议把 stdout/stderr 重定向到文件（避免 pipe 缓冲区写满导致阻塞）。
    """
    return subprocess.Popen(
        list(args),
        cwd=str(working_directory) if working_directory is not None else None,
        env=dict(env) if env is not None else None,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        text=bool(text_mode),
        encoding=encoding if text_mode else None,
        errors=errors if text_mode else None,
    )


def run_capture_script(project_root: Path, extra_args: Sequence[str] | None = None) -> int:
    """以子进程方式运行 `capture_beyondeditor.py`。

    Args:
        project_root: 仓库根目录（包含 capture_beyondeditor.py）。
        extra_args: 传给脚本的其他参数（当前脚本未解析参数，仅预留）。

    Returns:
        子进程返回码（0 表示成功）。
        
    Raises:
        FileNotFoundError: 当脚本文件不存在时抛出。
        
    注意：
        该功能目前为预留接口，实际环境中 capture_beyondeditor.py 脚本尚未提供。
        如需使用子进程隔离调用，请先实现该脚本。
    """
    script_path = project_root / "capture_beyondeditor.py"
    if not script_path.exists():
        raise FileNotFoundError(
            f"未找到脚本: {script_path}\n"
            f"提示：该功能为预留接口，用于在需要隔离 DPI/STDOUT 等全局副作用时调用独立脚本。\n"
            f"如需使用，请在项目根目录创建 capture_beyondeditor.py 并实现相应功能。"
        )

    cmd: list[str] = [sys.executable, str(script_path)]
    if extra_args:
        cmd += list(extra_args)

    result = run_process(cmd, working_directory=project_root, capture_output=False, text_mode=False)
    return int(result.exit_code)



