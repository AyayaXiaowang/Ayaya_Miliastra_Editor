from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    offenders: list[Path] = []

    for path in workspace_root.rglob("*.py"):
        relative = path.relative_to(workspace_root).as_posix()

        # 基础封装层允许直接使用 QDialog：
        # - base_widgets.py: 提供 BaseDialog / FormDialog 等统一对话框基类
        # - management_dialog_base.py: 管理类对话框公共骨架
        # - 本脚本自身
        if relative in {
            "app/ui/foundation/base_widgets.py",
            "app/ui/dialogs/management_dialog_base.py",
            "tools/check_no_direct_qdialog.py",
        }:
            continue

        text = path.read_text(encoding="utf-8")
        if "QDialog" in text:
            offenders.append(path)

    if offenders:
        print("Found direct QDialog usages (应优先继承 BaseDialog/FormDialog 或使用管理类对话框基类)：")
        for offender in sorted(offenders):
            print(f" - {offender}")
        sys.exit(1)

    print("OK: no direct QDialog usages outside对话框封装模块与本检查脚本。")


if __name__ == "__main__":
    main()



