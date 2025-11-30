"""
统一引擎版 节点图验证 CLI（推荐入口）

【职责定位】
本脚本为 CLI 包装层，仅负责：
1. 命令行参数解析（文件收集、开关处理）
2. 调用 `engine.validate.validate_files` 执行验证
3. 格式化输出验证结果

核心验证逻辑完全由 `engine.validate` 提供，本脚本不实现任何验证规则。

【实现说明】
- 通过 `from engine.validate import validate_files` 获取统一校验入口（兼容导出）
- 不再依赖 `core.validators.engine`；如需新增或修改规则，请在 `engine.validate.*` 中维护

【设计边界】
- 本脚本及其依赖的验证引擎只做 Graph Code 与节点图的**静态**语法/结构/连线校验，不会执行任何节点实现代码，也不尝试模拟游戏或服务器逻辑。
- 校验关注“节点是否存在、端口是否匹配、连线是否合理”等问题，目标是让 AI/开发者在写代码阶段就看到错误提示，而不是在本地复刻真实运行效果。

用法：
  - 全量（节点图 + 复合节点）：
      python -X utf8 tools/validate_graphs.py --all
  - 单文件/通配符：
      python -X utf8 tools/validate_graphs.py assets/资源库/节点图/server/某图.py
      python -X utf8 tools/validate_graphs.py "assets/资源库/节点图/**/*.py"
  - 行为开关：实体入参严格模式（仅允许连线/事件参数）
      python -X utf8 tools/validate_graphs.py --all --strict-entity-wire-only
"""

from __future__ import annotations

import sys
import io
from pathlib import Path
from typing import List

# 工作空间根目录（脚本位于 tools/ 下）
WORKSPACE = Path(__file__).resolve().parent.parent

# Windows 控制台输出编码为 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

# 导入引擎
sys.path.insert(0, str(WORKSPACE))
from engine.validate import validate_files


def _collect_all_targets(workspace: Path) -> List[Path]:
    files: List[Path] = []
    graphs_dir = workspace / "assets" / "资源库" / "节点图"
    composites_dir = workspace / "assets" / "资源库" / "复合节点库"
    if graphs_dir.exists():
        files.extend([p for p in graphs_dir.rglob("*.py")])
    if composites_dir.exists():
        files.extend([p for p in composites_dir.rglob("*.py")])
    return files


def main() -> None:
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    path_args = [a for a in args if not a.startswith("--")]

    # 实体入参严格模式（仅允许“连线/事件参数”）：与原 CLI 行为保持一致
    strict = ("--strict-entity-wire-only" in flags) or ("--strict" in flags)

    if (len(path_args) == 0) or ("--all" in flags) or ("ALL" in flags):
        targets = _collect_all_targets(WORKSPACE)
    else:
        pattern = path_args[0]
        if "*" in pattern or "?" in pattern:
            targets = list(WORKSPACE.glob(pattern))
        else:
            fp = WORKSPACE / pattern
            if not fp.exists():
                print(f"[ERROR] 文件不存在: {fp}")
                sys.exit(1)
            if fp.is_dir():
                print(f"[ERROR] 请输入文件或通配符，而不是目录: {fp}")
                sys.exit(1)
            targets = [fp]

    if not targets:
        target_desc = "assets/资源库/{节点图,复合节点库}/**/*.py" if (len(path_args) == 0) else path_args[0]
        print(f"[ERROR] 未找到匹配的文件: {target_desc}")
        sys.exit(1)

    print("=" * 80)
    print(f"开始验证 {len(targets)} 个文件（引擎）...")
    print("=" * 80)
    print()

    report = validate_files(
        targets,
        WORKSPACE,
        strict_entity_wire_only=strict,
    )

    failed_files = 0
    by_file: dict[str, list[str]] = {}
    for issue in report.issues:
        raw = issue.file or "<unknown>"
        # 统一为相对路径显示（不使用异常）
        prefix1 = str(WORKSPACE) + "\\"
        prefix2 = str(WORKSPACE) + "/"
        rel = raw
        if raw.startswith(prefix1):
            rel = raw[len(prefix1):]
        elif raw.startswith(prefix2):
            rel = raw[len(prefix2):]
        by_file.setdefault(rel, []).append(f"[{issue.category}/{issue.code}] {issue.message}")

    for f, msgs in sorted(by_file.items()):
        if msgs:
            failed_files += 1
            print(f"[FAILED] {f}")
            for m in msgs:
                print(f"  - {m}")
            print()

    passed_files = len(targets) - failed_files
    print("=" * 80)
    print("验证完成:")
    print(f"  总计: {len(targets)} 个文件")
    print(f"  通过: {passed_files} 个")
    print(f"  失败: {failed_files} 个")
    print("=" * 80)

    if failed_files > 0:
        sys.exit(1)
    print("\n[SUCCESS] 所有文件通过（引擎）")
    sys.exit(0)


if __name__ == "__main__":
    main()


