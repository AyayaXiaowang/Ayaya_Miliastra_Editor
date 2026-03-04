from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import ugc_file_tools_root


def _infer_graph_scope_from_id_int(graph_id_int: int) -> str:
    masked_value = int(graph_id_int) & 0xFF800000
    if masked_value == 0x40000000:
        return "server"
    if masked_value == 0x40800000:
        return "client"
    return "unknown"


def _load_json(file_path: Path) -> Any:
    return json.loads(file_path.read_text(encoding="utf-8"))


def _write_text(file_path: Path, text: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(text, encoding="utf-8")


def _load_node_type_semantic_map(mapping_path: Path) -> Dict[int, Dict[str, Any]]:
    mapping_object = _load_json(mapping_path)
    if not isinstance(mapping_object, dict):
        raise TypeError(f"node_type_semantic_map must be dict: {str(mapping_path)!r}")
    result: Dict[int, Dict[str, Any]] = {}
    for key, value in mapping_object.items():
        if isinstance(key, int):
            type_id_int = int(key)
        elif isinstance(key, str) and key.strip().isdigit():
            type_id_int = int(key.strip())
        else:
            continue
        if isinstance(value, dict):
            result[type_id_int] = dict(value)
    return result


def _extract_linear_flow_node_id_chain(parsed_graph: Any) -> List[int]:
    """
    从 package_parser 的 ParsedNodeGraph 中抽取线性 flow 链（node_id_int 顺序）。

    约束：
    - 仅支持：单入口 + 每个节点最多 1 条 outgoing flow；
    - 若图存在分支/多入口，直接抛错（后续再扩展）。
    """
    nodes = getattr(parsed_graph, "nodes", None)
    edges = getattr(parsed_graph, "edges", None)
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise TypeError("parsed_graph.nodes/edges must be list")

    node_id_set = set()
    for node in nodes:
        node_id_value = getattr(node, "node_id_int", None)
        if isinstance(node_id_value, int):
            node_id_set.add(int(node_id_value))

    flow_edges = [edge for edge in edges if getattr(edge, "edge_kind", "") == "flow"]
    next_by_src: Dict[int, int] = {}
    incoming: Dict[int, int] = {}

    for edge in flow_edges:
        src = getattr(edge, "src_node_id_int", None)
        dst = getattr(edge, "dst_node_id_int", None)
        if not isinstance(src, int) or not isinstance(dst, int):
            continue
        if int(src) not in node_id_set or int(dst) not in node_id_set:
            continue
        if int(src) in next_by_src and int(next_by_src[int(src)]) != int(dst):
            raise ValueError(f"non-linear flow: src node {src} has multiple outgoing flow edges")
        next_by_src[int(src)] = int(dst)
        incoming[int(dst)] = incoming.get(int(dst), 0) + 1

    if not next_by_src:
        raise ValueError("no flow edges found")

    start_candidates = sorted([src for src in next_by_src.keys() if incoming.get(int(src), 0) == 0])
    if len(start_candidates) != 1:
        raise ValueError(f"cannot find unique flow start: {start_candidates}")
    start = int(start_candidates[0])

    chain: List[int] = [start]
    seen: set[int] = {start}
    cursor = start
    while cursor in next_by_src:
        nxt = int(next_by_src[cursor])
        if nxt in seen:
            raise ValueError(f"cycle detected in flow chain at node {nxt}")
        chain.append(nxt)
        seen.add(nxt)
        cursor = nxt
    return chain


def _extract_reference_handler_body(reference_graph_code_path: Path) -> List[str]:
    """
    提取参考 Graph Code 的 `on_实体创建时` 方法 body（原样文本行）。
    用途：用于校准图的“可运行 Graph Code”复刻。
    """
    source_text = reference_graph_code_path.read_text(encoding="utf-8")
    module = ast.parse(source_text, filename=str(reference_graph_code_path))

    # 找到 class -> on_实体创建时
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "on_实体创建时":
                # 用 lineno/end_lineno 取原始切片（包含缩进）
                if not isinstance(item.lineno, int) or not isinstance(item.end_lineno, int):
                    raise ValueError("reference function lineno missing")
                lines = source_text.splitlines()
                start = int(item.lineno) - 1
                end = int(item.end_lineno)
                # body lines：去掉 def 行
                return lines[start + 1 : end]

    raise FileNotFoundError("reference graph code missing method: on_实体创建时")


def _render_graph_code_file(
    *,
    graph_id_text: str,
    graph_name: str,
    graph_type: str,
    description: str,
    reference_body_lines: List[str],
) -> str:
    """
    使用参考 handler body 生成一个“可运行 Graph Code”文件。
    说明：当前仅用于校准全节点覆盖图的复刻（后续再做通用编译器）。
    """
    class_name = str(graph_name or "").strip() or "自动解析_节点图"

    lines: List[str] = []
    lines.append('"""')
    lines.append(f"graph_id: {graph_id_text}")
    lines.append(f"graph_name: {graph_name}")
    lines.append(f"graph_type: {graph_type}")
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
    if graph_type == "client":
        lines.append("from app.runtime.engine.graph_prelude_client import *  # noqa: F401,F403")
    else:
        lines.append("from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403")
    lines.append("")
    lines.append("GRAPH_VARIABLES: list[GraphVariableConfig] = []")
    lines.append("")
    lines.append(f"class {class_name}:")
    lines.append("    def __init__(self, game, owner_entity):")
    lines.append("        self.game = game")
    lines.append("        self.owner_entity = owner_entity")
    lines.append("        validate_node_graph(self.__class__)")
    lines.append("")
    # 直接嵌入参考 body（它已带 8 空格缩进）
    lines.append("    def on_实体创建时(self, 事件源实体, 事件源GUID):")
    if not reference_body_lines:
        lines.append("        return")
    else:
        for body_line in reference_body_lines:
            # reference_body_lines 已包含缩进（至少 8 空格），原样输出
            lines.append(body_line)
    lines.append("")
    lines.append("    def register_handlers(self):")
    lines.append("        self.game.register_event_handler(")
    lines.append("            '实体创建时',")
    lines.append("            self.on_实体创建时,")
    lines.append("            owner=self.owner_entity,")
    lines.append("        )")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="将项目存档中的 pyugc 节点图（线性 flow 链）生成可运行 Graph Code（当前用于校准图复刻）。",
    )
    argument_parser.add_argument(
        "--package-root",
        dest="package_root",
        required=True,
        help="项目存档目录（例如 Graph_Generater/assets/资源库/项目存档/test4）",
    )
    argument_parser.add_argument(
        "--graph-id",
        dest="graph_id_int",
        type=int,
        required=True,
        help="pyugc 节点图 graph_id_int（例如 1073741826）",
    )
    argument_parser.add_argument(
        "--reference-graph-code",
        dest="reference_graph_code",
        required=True,
        help="参考 Graph Code 文件路径（用于复刻 handler 逻辑）",
    )
    argument_parser.add_argument(
        "--output-file",
        dest="output_file",
        default="",
        help="可选：输出 Graph Code 文件路径（默认写入到 <package>/节点图/<scope>/自动解析_节点图_<id>.py）",
    )
    argument_parser.add_argument(
        "--mapping-file",
        dest="mapping_file",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="typeId→节点名 映射文件路径（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    argument_parser.add_argument(
        "--validate",
        dest="validate",
        action="store_true",
        help="生成后使用引擎校验 Graph Code（等价于 validate_graph_code_for_package_root）。",
    )

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    package_root = Path(args.package_root).resolve()
    graph_id_int = int(args.graph_id_int)
    reference_graph_code_path = Path(args.reference_graph_code).resolve()
    mapping_path = Path(args.mapping_file).resolve()

    if not package_root.is_dir():
        raise FileNotFoundError(f"package_root not found: {str(package_root)!r}")
    if not reference_graph_code_path.is_file():
        raise FileNotFoundError(f"reference graph code not found: {str(reference_graph_code_path)!r}")
    if not mapping_path.is_file():
        raise FileNotFoundError(f"mapping file not found: {str(mapping_path)!r}")

    graph_scope = _infer_graph_scope_from_id_int(graph_id_int)
    if graph_scope not in {"server", "client"}:
        raise ValueError(f"unsupported graph_scope: {graph_scope!r} for graph_id_int={graph_id_int}")

    # 读取 parsed package
    from ugc_file_tools.package_parser import load_parsed_package

    parsed = load_parsed_package(package_root)
    graph = parsed.pyugc_node_graphs.get(int(graph_id_int))
    if graph is None:
        raise FileNotFoundError(f"graph_id_int not found in parsed package: {graph_id_int}")

    _mapping = _load_node_type_semantic_map(mapping_path)

    flow_chain = _extract_linear_flow_node_id_chain(graph)
    nodes_by_id: Dict[int, Any] = {int(n.node_id_int): n for n in graph.nodes if isinstance(getattr(n, "node_id_int", None), int)}

    # 将 flow 链节点（除入口事件）映射为节点名（用于基本一致性检查）
    flow_type_ids: List[int] = []
    flow_node_names: List[str] = []
    for node_id in flow_chain[1:]:
        node = nodes_by_id.get(int(node_id))
        if node is None:
            raise ValueError(f"flow node not found: node_id_int={node_id}")
        type_id = getattr(node, "node_def_id_int", None)
        if not isinstance(type_id, int):
            raise ValueError(f"node missing type id: node_id_int={node_id}")
        flow_type_ids.append(int(type_id))
        mapped = _mapping.get(int(type_id)) or {}
        node_name = str(mapped.get("graph_generater_node_name") or "").strip()
        if node_name == "":
            node_name = f"未识别节点类型_{int(type_id)}"
        flow_node_names.append(node_name)

    # 参考 handler body（用于复刻）
    reference_body_lines = _extract_reference_handler_body(reference_graph_code_path)

    package_namespace = package_root.name
    graph_name = str(getattr(graph, "graph_name", "") or "").strip() or f"自动解析_节点图_{graph_id_int}"
    graph_type = "server" if graph_scope == "server" else "client"
    graph_id_text = f"{graph_type}_graph_{int(graph_id_int)}__{package_namespace}"
    description = f"自动生成（pyugc→Graph Code）：复刻校准图 handler；flow_chain_nodes={len(flow_chain)}。"

    output_path_text = str(args.output_file or "").strip()
    if output_path_text != "":
        output_file_path = Path(output_path_text).resolve()
    else:
        output_file_path = package_root / "节点图" / graph_scope / f"自动解析_节点图_{int(graph_id_int)}.py"

    code_text = _render_graph_code_file(
        graph_id_text=graph_id_text,
        graph_name=graph_name,
        graph_type=graph_type,
        description=description,
        reference_body_lines=reference_body_lines,
    )
    _write_text(output_file_path, code_text)

    print("=" * 80)
    print("Graph Code 生成完成：")
    print(f"- package_root: {package_root}")
    print(f"- graph_id_int: {graph_id_int}")
    print(f"- output: {output_file_path}")
    print(f"- flow_nodes: {len(flow_chain)} (calls={len(flow_node_names)})")
    print("=" * 80)

    if bool(args.validate):
        from graph_code_validation import validate_graph_code_for_package_root
        report = validate_graph_code_for_package_root(package_root)
        print("Graph Code 校验完成：")
        print(f"- errors: {report.get('errors')}")
        print(f"- warnings: {report.get('warnings')}")
        if int(report.get("errors", 0) or 0) > 0:
            raise SystemExit(1)


if __name__ == "__main__":
    main()




