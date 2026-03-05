from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


def _find_graph_generater_root_from_package_root(package_root: Path) -> Optional[Path]:
    for parent in [package_root, *package_root.parents]:
        if (parent / "engine").is_dir() and (parent / "assets").is_dir() and (parent / "tools").is_dir():
            return parent

    # fallback：当项目存档被导出到 ugc_file_tools/out 下时，package_root 的父链不包含 Graph_Generater；
    # 此时尝试使用仓库根目录下的 Graph_Generater 作为验证工作区。
    from ugc_file_tools.repo_paths import try_find_graph_generater_root

    return try_find_graph_generater_root()


def collect_graph_code_files_for_package_root(package_root: Path) -> List[Path]:
    node_graph_root = Path(package_root).resolve() / "节点图"
    graph_directories = [
        node_graph_root / "client",
        node_graph_root / "server",
    ]

    collected: List[Path] = []
    for graph_directory in graph_directories:
        if not graph_directory.is_dir():
            continue
        for file_path in graph_directory.rglob("*.py"):
            if not file_path.is_file():
                continue
            if file_path.name.startswith("_"):
                continue
            if "校验" in file_path.stem:
                continue
            collected.append(file_path)
    return sorted(collected)


def validate_graph_code_for_package_root(
    package_root: Path,
    *,
    strict_entity_wire_only: bool = False,
) -> Dict[str, Any]:
    """
    使用 Graph_Generater 引擎验证节点图 Graph Code（静态校验，不执行节点逻辑）。

    返回：
    - dict：包含 errors/warnings 与完整 report（EngineIssue 列表 + stats/config）
    """
    package_root_path = Path(package_root).resolve()
    graph_generater_root = _find_graph_generater_root_from_package_root(package_root_path)
    if graph_generater_root is None:
        raise FileNotFoundError(
            "无法定位 Graph_Generater 根目录（需要包含 engine/assets/tools）："
            f"package_root={str(package_root_path)!r}"
        )

    graph_files = collect_graph_code_files_for_package_root(package_root_path)

    import sys

    graph_root_text = str(graph_generater_root.resolve())
    if graph_root_text not in sys.path:
        sys.path.insert(0, graph_root_text)

    from engine.configs.settings import settings
    from engine.validate import validate_files

    settings.set_config_path(graph_generater_root.resolve())

    report = validate_files(
        graph_files,
        workspace=graph_generater_root.resolve(),
        strict_entity_wire_only=bool(strict_entity_wire_only),
    )

    error_issues = [issue for issue in report.issues if issue.level == "error"]
    warning_issues = [issue for issue in report.issues if issue.level == "warning"]

    return {
        "package_root": str(package_root_path),
        "graph_generater_root": str(graph_generater_root.resolve()),
        "graph_files_count": len(graph_files),
        "errors": len(error_issues),
        "warnings": len(warning_issues),
        "report": report.to_dict(),
    }


