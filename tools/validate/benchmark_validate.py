"""
简单性能基准：统计全量验证耗时与问题数量。

用法：
  python -X utf8 -m tools.validate.benchmark_validate
"""
from __future__ import annotations

import sys
import io
import time
from pathlib import Path

# 工作空间根目录（脚本位于 tools/validate/ 下）
WORKSPACE = Path(__file__).resolve().parents[2]

# Windows 控制台输出编码为 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

if not __package__:
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m tools.validate.benchmark_validate\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

from engine.validate import (
    validate_files,
    enable_validation_profiling,
    reset_validation_profiling_stats,
    get_validation_profiling_stats,
)  # noqa: E402
from engine.configs.settings import settings  # noqa: E402

# 为布局/注册表上下文等依赖 workspace_root 的模块提供入口信息
settings.set_config_path(WORKSPACE)


def _collect_all_targets(workspace: Path) -> list[Path]:
    files: list[Path] = []
    gdir = workspace / "assets" / "资源库" / "节点图"
    cdir = workspace / "assets" / "资源库" / "复合节点库"
    if gdir.exists():
        files.extend([p for p in gdir.rglob("*.py")])
    if cdir.exists():
        files.extend([p for p in cdir.rglob("*.py")])
    return files


def main() -> int:
    targets = _collect_all_targets(WORKSPACE)
    if not targets:
        print("[ERROR] 未找到任何待验证文件。")
        return 1
    reset_validation_profiling_stats()
    enable_validation_profiling(True)

    t0 = time.perf_counter()
    report = validate_files(targets, WORKSPACE, strict_entity_wire_only=False)
    t1 = time.perf_counter()

    enable_validation_profiling(False)
    total = len(targets)
    errors = len([i for i in report.issues if i.level == "error"])
    warnings = len([i for i in report.issues if i.level == "warning"])
    print("=" * 80)
    print("性能基准（引擎化校验）")
    print(f"  文件数: {total}")
    print(f"  错误: {errors}")
    print(f"  警告: {warnings}")
    print(f"  耗时: {(t1 - t0):.3f}s")
    print("=" * 80)

    stats = get_validation_profiling_stats()
    if stats:
        print("\n规则级耗时统计（按总耗时降序）：")
        sorted_items = sorted(
            stats.items(),
            key=lambda item: item[1].get("time", 0.0),
            reverse=True,
        )
        for rule_id, data in sorted_items:
            total_time = float(data.get("time", 0.0))
            calls = int(data.get("calls", 0.0))
            avg_time = (total_time / calls) if calls > 0 else 0.0
            print(f"- {rule_id}: 总耗时 {total_time:.4f}s, 调用 {calls} 次, 平均 {avg_time:.6f}s/次")
        print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())


