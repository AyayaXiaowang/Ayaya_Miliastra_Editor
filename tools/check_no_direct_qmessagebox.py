from __future__ import annotations

import sys
from pathlib import Path


ALLOWED_FILES = {
    "app/ui/foundation/dialog_utils.py",
    "tools/check_no_direct_qmessagebox.py",
}


def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    offenders: list[Path] = []

    for path in workspace_root.rglob("*.py"):
        relative = path.relative_to(workspace_root).as_posix()
        if relative in ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if "QMessageBox" in text:
            offenders.append(path)

    if offenders:
        print("Found direct QMessageBox usages (should go through ui.foundation.dialog_utils):")
        for offender in sorted(offenders):
            print(f" - {offender}")
        sys.exit(1)

    print("OK: no direct QMessageBox usages outside ui.foundation.dialog_utils.")


if __name__ == "__main__":
    main()


