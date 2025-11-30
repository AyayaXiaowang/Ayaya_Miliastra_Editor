"""检查所有实现函数是否声明了 @node_spec。

用法：
    python tools/check_impl_node_specs.py

返回非零码请直接抛错（本脚本不吞异常）。
"""

from __future__ import annotations

import inspect
import importlib
from pathlib import Path
import sys


def main() -> None:
    # 确保可从项目根导入实现包
    workspace = Path(__file__).parent.parent
    sys.path.insert(0, str(workspace))
    pkg = importlib.import_module("node_implementations")
    missing = []

    for name, obj in inspect.getmembers(pkg, inspect.isfunction):
        module_name = getattr(obj, "__module__", "")
        # 只检查实现包内的函数
        if not module_name.startswith("node_implementations."):
            continue
        if not hasattr(obj, "__node_spec__"):
            missing.append(f"{module_name}.{name}")

    if len(missing) > 0:
        print("[ERROR] 以下实现函数缺少 @node_spec:")
        for item in missing:
            print(f"  - {item}")
        # 非零退出码由异常触发
        raise SystemExit(1)

    print("[OK] 所有实现函数均已声明 @node_spec")


if __name__ == "__main__":
    main()


