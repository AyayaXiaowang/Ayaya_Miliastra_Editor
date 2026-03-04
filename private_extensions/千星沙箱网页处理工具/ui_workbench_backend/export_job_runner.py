from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def run_ui_workbench_export_job_in_subprocess(*, bridge: object, command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    在子进程中执行 UI Workbench 导出任务（隔离可能持有 GIL/DLL 的写回/校验逻辑，避免主进程 UI 卡死）。

    返回结构与旧实现保持一致：
      - {"exit_code": int, "stderr_tail": list[str], "report": dict|None}
    """
    import subprocess
    import sys
    import tempfile
    from collections import deque
    from uuid import uuid4

    backend_dir = Path(getattr(bridge, "get_workbench_backend_dir")()).resolve()
    if not backend_dir.is_dir():
        raise FileNotFoundError(str(backend_dir))

    script_path = (backend_dir / "run_ui_workbench_export_job.py").resolve()
    if not script_path.is_file():
        raise FileNotFoundError(str(script_path))

    package_id_text = ""
    main_window = getattr(bridge, "_main_window", None)
    package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
    current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
    if current_package_id is not None:
        package_id_text = str(current_package_id or "").strip()

    job = {
        "command": str(command),
        "package_id": str(package_id_text),
        "payload": dict(payload),
    }

    with tempfile.TemporaryDirectory(prefix="ui_workbench_export_job_") as tmpdir:
        job_file = (Path(tmpdir) / f"job_{uuid4().hex[:10]}.json").resolve()
        report_file = (Path(tmpdir) / f"report_{uuid4().hex[:10]}.json").resolve()
        job_file.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

        creationflags = 0
        if os.name == "nt":
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)

        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(script_path), "--job", str(job_file), "--report", str(report_file)],
            cwd=str(backend_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )

        tail = deque(maxlen=240)
        stderr = proc.stderr
        if stderr is not None:
            for raw_line in stderr:
                line = str(raw_line).rstrip("\n")
                if line.strip():
                    tail.append(line)

        exit_code = int(proc.wait())
        if exit_code != 0:
            return {"exit_code": int(exit_code), "stderr_tail": list(tail), "report": None}

        if not report_file.is_file():
            raise FileNotFoundError(str(report_file))
        report = json.loads(report_file.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise TypeError("export job report must be dict")
        return {"exit_code": int(exit_code), "stderr_tail": list(tail), "report": dict(report)}

