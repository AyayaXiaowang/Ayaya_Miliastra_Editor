from __future__ import annotations

"""
ugc_file_tools.graph.code_generation_impl

从项目存档目录批量生成 Graph_Generater Graph Code（Python 类结构）。

核心原则：
- **GraphModel → Graph Code** 的唯一真源为 `app.codegen.ExecutableCodeGenerator`（本模块通过 ugc_file_tools 的薄转发调用）；
- **pyugc → GraphModel** 的唯一真源为 `ugc_file_tools.graph.pyugc_graph_model_builder`；
- 对于映射缺失导致无法构建 GraphModel 的图，生成“可校验的占位 Graph Code”，避免全链路阻断。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from ugc_file_tools.graph.pyugc_graph_model_builder import (
    build_graph_model_from_pyugc_graph,
    find_pyugc_graph_json_for_graph_id,
    infer_graph_scope_from_id_int,
    load_node_type_semantic_map,
)
from ugc_file_tools.graph_codegen import ExecutableCodeGenerator
from ugc_file_tools.repo_paths import resolve_graph_generater_root, ugc_file_tools_root


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_placeholder_graph_code_file(graph_file_path: Path) -> bool:
    if not graph_file_path.is_file():
        return False
    content = graph_file_path.read_text(encoding="utf-8")
    return "占位节点图" in content


def _find_pyugc_raw_graph_rel_path(package_root: Path, graph_id_int: int) -> str:
    raw_graphs_dir = package_root / "节点图" / "原始解析" / "pyugc_graphs"
    if not raw_graphs_dir.is_dir():
        return ""
    candidates = sorted(
        list(raw_graphs_dir.glob(f"graph_{int(graph_id_int)}_*.json")),
        key=lambda path: path.name.casefold(),
    )
    if not candidates:
        return ""
    return str(candidates[0].relative_to(package_root)).replace("\\", "/")


def _extract_type_id_int_from_pyugc_node_payload(node_payload: Any) -> int:
    if not isinstance(node_payload, dict):
        raise TypeError("node_payload must be dict")
    node_id_value = node_payload.get("node_id_int")
    if not isinstance(node_id_value, int):
        raise ValueError("node missing node_id_int")

    data_2 = node_payload.get("data_2")
    if not isinstance(data_2, dict):
        raise ValueError(f"node missing data_2: node_id_int={int(node_id_value)}")
    decoded_2 = data_2.get("decoded")
    if not isinstance(decoded_2, dict):
        raise ValueError(f"node missing data_2.decoded: node_id_int={int(node_id_value)}")
    field_5 = decoded_2.get("field_5")
    if not isinstance(field_5, dict) or not isinstance(field_5.get("int"), int):
        raise ValueError(f"node missing type id: node_id_int={int(node_id_value)}")
    return int(field_5.get("int"))


def _collect_unmapped_type_ids_from_pyugc_graph(
    *,
    graph_payload: Dict[str, Any],
    mapping: Dict[int, Dict[str, Any]],
) -> List[int]:
    decoded_nodes = graph_payload.get("decoded_nodes")
    if not isinstance(decoded_nodes, list):
        raise TypeError("decoded_nodes missing or invalid")

    missing: set[int] = set()
    for node_payload in decoded_nodes:
        type_id_int = _extract_type_id_int_from_pyugc_node_payload(node_payload)
        mapped = mapping.get(int(type_id_int)) or {}
        node_name = str(mapped.get("graph_generater_node_name") or "").strip()
        if node_name == "":
            missing.add(int(type_id_int))
    return sorted(missing)


def _render_main_validate_cli_lines() -> List[str]:
    return [
        "if __name__ == '__main__':",
        "    from app.runtime.engine.node_graph_validator import validate_file_cli",
        "    raise SystemExit(validate_file_cli(__file__))",
    ]


def _render_placeholder_graph_code_text(
    *,
    package_namespace: str,
    graph_id_int: int,
    graph_name: str,
    graph_scope: str,
    missing_type_ids: Sequence[int],
    pyugc_raw_graph_rel_path: str,
) -> str:
    scope = str(graph_scope or "server").strip().lower()
    if scope not in {"server", "client"}:
        raise ValueError(f"unsupported graph_scope: {graph_scope!r}")

    graph_id_text = f"{scope}_graph_{int(graph_id_int)}__{package_namespace}"
    graph_name_text = str(graph_name or "").strip() or f"自动解析_节点图_{int(graph_id_int)}"
    class_name = f"自动解析_节点图_{int(graph_id_int)}"

    # 事件选择：
    # - server：用最常见的 “实体创建时”
    # - client：用 client 图常见锚点 “节点图开始”
    event_title = "节点图开始" if scope == "client" else "实体创建时"

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

    missing_text = ",".join(str(int(x)) for x in list(missing_type_ids or [])[:80])
    if len(list(missing_type_ids or [])) > 80:
        missing_text = f"{missing_text},..."

    lines: List[str] = []
    lines.append('"""')
    lines.append(f"graph_id: {graph_id_text}")
    lines.append(f"graph_name: {graph_name_text}")
    lines.append(f"graph_type: {scope}")
    lines.append(
        "description: "
        "自动生成占位节点图（占位节点图）：因节点类型映射缺失，无法从 pyugc_graphs 构建完整 GraphModel。"
    )
    if missing_text:
        lines.append(f"missing_node_type_ids: {missing_text}")
    if str(pyugc_raw_graph_rel_path or "").strip() != "":
        lines.append(f"pyugc_raw_graph: {str(pyugc_raw_graph_rel_path).strip()}")
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
    lines.extend(_render_main_validate_cli_lines())
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
    if event_title == "实体创建时":
        lines.append("    def on_实体创建时(self, 事件源实体, 事件源GUID):")
    else:
        lines.append(f"    def on_{event_title}(self):")
    lines.append("        return")
    lines.append("")
    lines.append("    def register_handlers(self):")
    if scope == "server":
        lines.append("        self.game.register_event_handler(")
        lines.append(f"            {event_title!r},")
        lines.append(f"            self.on_{event_title},")
        lines.append("            owner=self.owner_entity,")
        lines.append("        )")
        lines.append("        return")
    else:
        lines.append("        # client 节点图通常由外部调度触发；占位图不显式注册事件")
        lines.append("        return")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _refresh_graph_dir_claude(*, graph_dir: Path, scope: str) -> None:
    graph_files = [
        path for path in graph_dir.rglob("*.py") if path.is_file() and (not path.name.startswith("_")) and ("校验" not in path.stem)
    ]
    graph_count = len(graph_files)

    scope_text = str(scope or "").strip().lower()
    scope_label = "client" if scope_text == "client" else "server"

    lines: List[str] = []
    lines.append("## 目录用途")
    lines.append(f"- 存放 {scope_label} 侧节点图（Graph Code，Python 类结构）。")
    lines.append("")
    lines.append("## 当前状态")
    lines.append(f"- 当前包含 {graph_count} 个节点图文件（不含辅助脚本）。")
    lines.append("")
    lines.append("## 注意事项")
    lines.append("- 节点图文件需通过 `python -X utf8 -m app.cli.graph_tools validate-file <path>` 或 validate-graphs 校验后再投入使用。")
    lines.append("- 本文件不记录修改历史，仅保持用途/状态/注意事项的实时描述。")
    lines.append("")
    lines.append("---")
    lines.append("注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。")
    lines.append("")

    claude_file_path = graph_dir / "claude.md"
    claude_file_path.write_text("\n".join(lines), encoding="utf-8")


def generate_graph_code_for_package_root(package_root_path: Path, *, overwrite: bool) -> Dict[str, Any]:
    package_root = Path(package_root_path).resolve()
    if not package_root.is_dir():
        raise FileNotFoundError(f"package_root not found: {str(package_root)!r}")

    graph_generater_root = resolve_graph_generater_root(package_root)

    mapping_path = (ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json").resolve()
    if not mapping_path.is_file():
        raise FileNotFoundError(f"node_type_semantic_map not found: {str(mapping_path)!r}")
    mapping = load_node_type_semantic_map(mapping_path)

    output_client_dir = package_root / "节点图" / "client"
    output_server_dir = package_root / "节点图" / "server"
    output_client_dir.mkdir(parents=True, exist_ok=True)
    output_server_dir.mkdir(parents=True, exist_ok=True)

    codegen = ExecutableCodeGenerator(graph_generater_root.resolve())

    generated_files: List[Path] = []
    skipped_files: List[Path] = []

    index_path = package_root / "节点图" / "原始解析" / "pyugc_graphs_index.json"
    index_obj = _load_json(index_path)
    if not isinstance(index_obj, list):
        raise TypeError(f"pyugc_graphs_index.json format error: {str(index_path)!r}")

    graph_ids: List[int] = []
    for entry in index_obj:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("graph_id_int"), int):
            graph_ids.append(int(entry.get("graph_id_int")))
    graph_ids = sorted(set(graph_ids))

    for graph_id_int in graph_ids:
        graph_scope = infer_graph_scope_from_id_int(graph_id_int)
        output_dir = output_client_dir if graph_scope == "client" else output_server_dir
        output_file_path = output_dir / f"自动解析_节点图_{int(graph_id_int)}.py"

        if output_file_path.exists() and (not bool(overwrite)) and (not _is_placeholder_graph_code_file(output_file_path)):
            skipped_files.append(output_file_path)
            continue

        graph_json_path = find_pyugc_graph_json_for_graph_id(package_root, graph_id_int)
        graph_payload = _load_json(graph_json_path)
        if not isinstance(graph_payload, dict):
            raise TypeError(f"pyugc graph json must be dict: {str(graph_json_path)!r}")

        missing_type_ids = _collect_unmapped_type_ids_from_pyugc_graph(graph_payload=graph_payload, mapping=mapping)
        if missing_type_ids:
            graph_code_text = _render_placeholder_graph_code_text(
                package_namespace=package_root.name,
                graph_id_int=graph_id_int,
                graph_name=str(graph_payload.get("graph_name") or ""),
                graph_scope=graph_scope,
                missing_type_ids=missing_type_ids,
                pyugc_raw_graph_rel_path=_find_pyugc_raw_graph_rel_path(package_root, graph_id_int),
            )
            output_file_path.write_text(graph_code_text, encoding="utf-8")
            generated_files.append(output_file_path)
            continue

        graph_model, metadata = build_graph_model_from_pyugc_graph(
            package_root=package_root,
            graph_id_int=graph_id_int,
            mapping_path=mapping_path,
        )
        graph_code_text = codegen.generate_code(graph_model, metadata=metadata)
        output_file_path.write_text(graph_code_text, encoding="utf-8")
        generated_files.append(output_file_path)

    _refresh_graph_dir_claude(graph_dir=output_client_dir, scope="client")
    _refresh_graph_dir_claude(graph_dir=output_server_dir, scope="server")

    return {
        "package_name": package_root.name,
        "output_client_dir": output_client_dir,
        "output_server_dir": output_server_dir,
        "generated_files": generated_files,
        "skipped_files": skipped_files,
    }

