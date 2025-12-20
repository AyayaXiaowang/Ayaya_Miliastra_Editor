from __future__ import annotations

# ============================================================
# 崩溃诊断：启用 faulthandler 以捕获 C 扩展段错误时的调用栈
# ============================================================
import faulthandler
import sys
faulthandler.enable(file=sys.stderr, all_threads=True)
print("[DEBUG] faulthandler 已启用，C 扩展崩溃时将打印调用栈", file=sys.stderr, flush=True)

import os
import runpy
from pathlib import Path


def main() -> None:
    # 确保工作目录为项目根目录（便于 VSCode “运行当前文件/调试当前文件”）
    workspace_root = Path(__file__).resolve().parent
    os.chdir(workspace_root)

    # 以模块方式执行，确保 __package__/__spec__ 正确，满足 app.cli.run_app 的运行约束
    runpy.run_module("app.cli.run_app", run_name="__main__")


if __name__ == "__main__":
    main()


