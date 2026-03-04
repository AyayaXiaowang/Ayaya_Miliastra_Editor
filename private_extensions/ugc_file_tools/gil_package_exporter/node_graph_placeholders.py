from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .file_io import _ensure_directory, _sanitize_filename, _write_json_file, _write_text_file


def _is_placeholder_graph_code_file(graph_file_path: Path) -> bool:
    if not graph_file_path.is_file():
        return False
    content = graph_file_path.read_text(encoding="utf-8")
    return "占位节点图" in content


def _build_placeholder_node_graph_file_text(
    *,
    graph_id: str,
    graph_name: str,
    graph_type: str,
    description: str,
) -> str:
    scope = str(graph_type or "server").strip().lower()
    if scope not in {"server", "client"}:
        raise ValueError(f"unsupported graph_type: {graph_type!r}")

    class_name = _sanitize_filename(graph_name, max_length=80).replace("-", "_")
    if not class_name or class_name[0].isdigit():
        class_name = f"自动解析_节点图_{graph_id}"

    prelude_import = (
        "from app.runtime.engine.graph_prelude_client import *  # noqa: F401,F403"
        if scope == "client"
        else "from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403"
    )
    prelude_runtime = (
        "from app.runtime.engine.graph_prelude_client import GameRuntime"
        if scope == "client"
        else "from app.runtime.engine.graph_prelude_server import GameRuntime"
    )

    lines: List[str] = []
    lines.append('"""')
    lines.append(f"graph_id: {graph_id}")
    lines.append(f"graph_name: {graph_name}")
    lines.append(f"graph_type: {scope}")
    lines.append(f"description: {description}")
    lines.append('"""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")

    from engine.utils.workspace import render_workspace_bootstrap_lines

    lines.extend(
        render_workspace_bootstrap_lines(
            project_root_var="PROJECT_ROOT",
            assets_root_var="ASSETS_ROOT",
        )
    )
    lines.append("")
    lines.append("if __name__ == '__main__':")
    lines.append("    from app.runtime.engine.node_graph_validator import validate_file_cli")
    lines.append("    raise SystemExit(validate_file_cli(__file__))")
    lines.append("")
    lines.append(prelude_import)
    lines.append(prelude_runtime)
    lines.append("")
    lines.append("GRAPH_VARIABLES: list[GraphVariableConfig] = []")
    lines.append("")
    lines.append("")
    lines.append(f"class {class_name}:")
    lines.append("    def __init__(self, game, owner_entity):")
    lines.append("        self.game = game")
    lines.append("        self.owner_entity = owner_entity")
    lines.append("        return")
    lines.append("")
    lines.append("    def on_实体创建时(self, 事件源实体, 事件源GUID):")
    lines.append("        # 占位节点图：未还原实际逻辑；仅用于让图ID可被索引与校验。")
    lines.append("        return")
    lines.append("")
    lines.append("    def register_handlers(self):")
    lines.append("        self.game.register_event_handler(")
    lines.append("            \"实体创建时\",")
    lines.append("            self.on_实体创建时,")
    lines.append("            owner=self.owner_entity,")
    lines.append("        )")
    lines.append("        return")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _refresh_node_graph_dir_claude(node_graph_dir: Path, graph_type: str) -> None:
    scope = str(graph_type or "server").strip().lower()
    if scope not in {"server", "client"}:
        raise ValueError(f"unsupported graph_type: {graph_type!r}")

    graph_files = [
        path
        for path in node_graph_dir.rglob("*.py")
        if path.is_file() and (not path.name.startswith("_")) and ("校验" not in path.stem)
    ]
    graph_count = len(graph_files)

    lines: List[str] = []
    lines.append("## 目录用途")
    lines.append(f"- 存放 {scope} 侧节点图（Graph Code，Python 类结构）。")
    lines.append("")
    lines.append("## 当前状态")
    lines.append(f"- 当前包含 {graph_count} 个节点图文件（不含辅助脚本）。")
    lines.append("")
    lines.append("## 注意事项")
    lines.append("- 节点图文件需通过 `python -X utf8 -m app.cli.graph_tools validate-file <path>` 或 validate-graphs 校验后再投入使用。")
    lines.append("- 本文件不记录修改历史，仅保持用途/状态/注意事项的实时描述。")
    lines.append("")
    lines.append("---")
    lines.append("注意：本文件不记录修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。")
    lines.append("")
    _write_text_file(node_graph_dir / "claude.md", "\n".join(lines))


def _export_placeholder_node_graphs_from_references(
    *,
    output_package_root: Path,
    package_namespace: str,
    referenced_graph_sources: Dict[int, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    server_dir = output_package_root / "节点图" / "server"
    client_dir = output_package_root / "节点图" / "client"
    _ensure_directory(server_dir)
    _ensure_directory(client_dir)

    exported: List[Dict[str, Any]] = []

    for graph_id_int, sources in sorted(referenced_graph_sources.items(), key=lambda item: item[0]):
        graph_id_text = f"server_graph_{int(graph_id_int)}__{package_namespace}"
        graph_name_text = f"自动解析_节点图_{int(graph_id_int)}"
        source_names = [
            str(source_item.get("skill_name", ""))
            for source_item in (sources or [])
            if isinstance(source_item, dict)
        ]
        unique_source_names = [name for name in source_names if name]
        unique_source_names = list(dict.fromkeys(unique_source_names))
        preview_sources = "，".join(unique_source_names[:3])
        suffix = f"（等{len(unique_source_names)}处）" if len(unique_source_names) > 3 else ""
        description_text = (
            f"自动生成占位节点图：来自技能挂载引用 graph_id_int={int(graph_id_int)}；来源: {preview_sources}{suffix}"
            if preview_sources
            else f"自动生成占位节点图：来自技能挂载引用 graph_id_int={int(graph_id_int)}"
        )
        description_text = (
            f"{description_text}；注意：该 graph_id 未在 pyugc dump 中定位到图定义（仅在引用中出现），因此无法自动还原图内节点与连线。"
        )

        file_stem = _sanitize_filename(graph_name_text, max_length=120)
        graph_file_path = server_dir / f"{file_stem}.py"
        if graph_file_path.exists() and (not _is_placeholder_graph_code_file(graph_file_path)):
            continue

        code_text = _build_placeholder_node_graph_file_text(
            graph_id=graph_id_text,
            graph_name=graph_name_text,
            graph_type="server",
            description=description_text,
        )
        _write_text_file(graph_file_path, code_text)
        exported.append(
            {
                "graph_id_int": int(graph_id_int),
                "graph_id": graph_id_text,
                "graph_name": graph_name_text,
                "graph_type": "server",
                "output": str(graph_file_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    _refresh_node_graph_dir_claude(server_dir, "server")
    _refresh_node_graph_dir_claude(client_dir, "client")

    placeholder_index_path = output_package_root / "节点图" / "原始解析" / "placeholder_graphs_index.json"
    _write_json_file(placeholder_index_path, exported)
    return exported


