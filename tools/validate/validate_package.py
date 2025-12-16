"""存档级综合校验（CLI） - 等同于在 UI 中点击“验证”的“存档包部分”。

职责定位（CLI 包装层，仅做编排与输出）：
1) 基于 PackageIndex / PackageView 对每个存档包执行综合校验；
2) 聚焦关卡实体 / 模板 / 实例 / 管理配置 / 节点图挂载关系等“存档包 JSON”层面的结构与引用一致性；
3) 汇总并格式化输出（带颜色/统计/逐存档）。

注意：
- 本脚本不再对节点图源码做代码规范/语法级静态校验；
- 节点图内部错误请使用统一入口 `tools/validate/validate_graphs.py` 或编辑器内的节点图校验功能。

用法：
    python -X utf8 -m tools.validate.validate_package
"""

import sys
import io
from pathlib import Path

if not __package__:
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m tools.validate.validate_package\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

# 统一工作空间根目录（脚本位于 tools/validate/ 下）
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# 修复 Windows 控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from typing import List, Tuple

from engine.validate import ComprehensiveValidator
from engine.resources import PackageIndexManager, PackageView, ResourceManager, build_resource_context


# ANSI颜色码
class Colors:
    RED = '\u001b[31m'
    YELLOW = '\u001b[33m'
    GREEN = '\u001b[32m'
    BLUE = '\u001b[34m'
    CYAN = '\u001b[36m'
    RESET = '\u001b[0m'
    BOLD = '\u001b[1m'


def print_colored(text: str, color: str = Colors.RESET) -> None:
    """打印带颜色的文本。"""
    print(f"{color}{text}{Colors.RESET}")


def _validate_packages(
    resource_manager: ResourceManager,
    package_views: List[PackageView],
) -> Tuple[int, int]:
    """对所有存档包执行综合校验（仅输出存档级问题），返回（错误数，警告数）。"""
    if not package_views:
        print_colored(
            "未找到任何存档包索引（assets/资源库/功能包索引/pkg_*.json），跳过存档包校验。",
            Colors.YELLOW,
        )
        return 0, 0

    print_colored(f"发现 {len(package_views)} 个存档包，开始逐个校验...", Colors.BLUE)

    # 仅保留的类别：聚焦在“存档包 JSON + 资源挂载关系 + 信号定义/使用约束”层面的问题
    allowed_categories = {
        "关卡实体",
        "模板",
        "实例",
        "管理配置",
        "节点图挂载",
        "信号系统",
    }

    total_errors = 0
    total_warnings = 0

    for package_view in package_views:
        validator = ComprehensiveValidator(package_view, resource_manager, verbose=False)
        issues = validator.validate_all()
        # 只展示指定类别的问题，过滤掉节点图内部结构/端口等低层细节
        display_issues = [issue for issue in issues if issue.category in allowed_categories]

        error_count = sum(1 for issue in display_issues if issue.level == "error")
        warning_count = sum(1 for issue in display_issues if issue.level == "warning")
        info_count = sum(1 for issue in display_issues if issue.level == "info")
        total_issues = len(display_issues)

        total_errors += error_count
        total_warnings += warning_count

        print_colored(
            f"\n存档 '{package_view.name}' ({package_view.package_id})", Colors.BOLD
        )
        if not display_issues:
            print_colored("  ✅ 未发现与存档索引或挂载关系相关的问题。", Colors.GREEN)
            continue

        print_colored(
            f"  发现 {total_issues} 个问题：错误 {error_count}，警告 {warning_count}，提示 {info_count}。",
            Colors.YELLOW,
        )

        for issue in display_issues:
            if issue.level == "error":
                icon = "❌"
                color = Colors.RED
            elif issue.level == "warning":
                icon = "⚠️"
                color = Colors.YELLOW
            else:
                icon = "ℹ️"
                color = Colors.BLUE
            location_text = issue.location or ""
            header = f"{icon} [{issue.category}] {location_text}".strip()
            print_colored(f"  {header}", color)
            print(f"     {issue.message}")
            suggestion_text = getattr(issue, "suggestion", "")
            if suggestion_text:
                print_colored(f"     💡 {suggestion_text}", Colors.CYAN)

    print()
    return total_errors, total_warnings


def main() -> None:
    """主函数：执行存档包级综合校验（不做节点图源码静态检查）。"""
    workspace_path = WORKSPACE_ROOT

    print_colored("\n" + "=" * 70, Colors.CYAN)
    print_colored("存档级综合校验（仅存档索引与挂载关系）", Colors.CYAN + Colors.BOLD)
    print_colored("=" * 70 + "\n", Colors.CYAN)

    resource_manager, _, package_views = build_resource_context(workspace_path)
    package_error_count, package_warning_count = _validate_packages(
        resource_manager,
        package_views,
    )

    # 综合结果与退出码
    total_error_count = package_error_count
    total_warning_count = package_warning_count

    print_colored("=" * 70, Colors.CYAN)
    print_colored("综合结果", Colors.CYAN + Colors.BOLD)
    print_colored("=" * 70 + "\n", Colors.CYAN)

    if total_error_count == 0:
        print_colored("✅ 验证通过：存档级校验没有错误。", Colors.GREEN + Colors.BOLD)
        if total_warning_count > 0:
            print_colored(
                f"⚠️ 共有 {total_warning_count} 条警告，请根据上文提示检查。",
                Colors.YELLOW,
            )
        print()
        sys.exit(0)

    print_colored(
        f"❌ 存在 {total_error_count} 条错误（均为存档级问题）。",
        Colors.RED + Colors.BOLD,
    )
    if total_warning_count > 0:
        print_colored(
            f"⚠️ 同时存在 {total_warning_count} 条警告。",
            Colors.YELLOW,
        )
    print()
    sys.exit(1)


if __name__ == "__main__":
    main()


