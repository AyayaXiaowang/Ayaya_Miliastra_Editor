from __future__ import annotations

"""
graph_cache 结构一致性检查脚本。

功能：
- 校验 graph_cache JSON 中的 nodes / edges / 端口名称是否自洽；
- 列出：
  - 幽灵节点（edges 引用的节点 ID 在 nodes 中不存在）；
  - 端口不匹配（edges 上的 src_port/dst_port 不在对应节点的输出/输入端口集合内，考虑流程占位符）；
  - 孤立节点（在任何一条边中都未出现的节点）。

用法（在项目根目录运行）：
  python -m tools.validate.validate_graph_cache_integrity                # 扫描 app/runtime/cache/graph_cache 下所有 .json
  python -m tools.validate.validate_graph_cache_integrity path/to/file.json [more.json ...]
  python -m tools.validate.validate_graph_cache_integrity app/runtime/cache/graph_cache
"""

import json
import sys
import io
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 工作空间根目录（脚本位于 tools/validate/ 下）
WORKSPACE = Path(__file__).resolve().parents[2]

# Windows 控制台输出编码为 UTF-8（与其他 tools 保持一致）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

if not __package__:
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m tools.validate.validate_graph_cache_integrity\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

from engine.graph.common import (  # type: ignore[import]
    FLOW_BRANCH_PORT_ALIASES,
    FLOW_IN_PORT_NAMES,
    FLOW_OUT_PORT_NAMES,
    FLOW_PORT_PLACEHOLDER,
)


def _extract_graph_data(raw: Dict) -> Dict:
    """
    从 graph_cache 或单纯的 graph_data 结构中提取带 nodes/edges 的 graph_data。
    允许三种输入形态：
    - 顶层即 graph_data（包含 nodes/edges）；
    - 顶层是 result_data（graph_id/name/... + data）；
    - 顶层是带 file_hash/node_defs_fp 的持久化缓存结构。
    """
    if "nodes" in raw and "edges" in raw:
        return raw

    if "data" in raw:
        data_obj = raw["data"]
        if isinstance(data_obj, dict) and "nodes" in data_obj and "edges" in data_obj:
            return data_obj

    if "result_data" in raw:
        result_data = raw["result_data"]
        if isinstance(result_data, dict) and "data" in result_data:
            data_obj = result_data["data"]
            if isinstance(data_obj, dict) and "nodes" in data_obj and "edges" in data_obj:
                return data_obj

    raise ValueError("输入 JSON 不包含可识别的 graph_data 结构（缺少 nodes/edges）")


def _load_json(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _analyze_graph_data(graph_data: Dict) -> Tuple[bool, Dict]:
    """
    对单个 graph_data 做结构一致性检查。

    返回：
    - has_error: 是否存在严重结构问题（幽灵节点 / 端口不匹配）；
    - report: 结构化结果字典，包含各类问题清单。
    """
    nodes = graph_data.get("nodes")
    edges = graph_data.get("edges")

    if not isinstance(nodes, list):
        raise ValueError("graph_data['nodes'] 必须是列表")
    if not isinstance(edges, list):
        raise ValueError("graph_data['edges'] 必须是列表")

    node_by_id: Dict[str, Dict] = {}
    input_ports_by_id: Dict[str, Set[str]] = {}
    output_ports_by_id: Dict[str, Set[str]] = {}

    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("nodes 列表中的元素必须是对象")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("每个节点必须包含非空字符串类型的 id 字段")
        if node_id in node_by_id:
            raise ValueError(f"检测到重复的节点 ID: {node_id}")

        node_by_id[node_id] = node

        inputs = node.get("inputs") or []
        outputs = node.get("outputs") or []

        if not isinstance(inputs, list) or not isinstance(outputs, list):
            raise ValueError("节点的 inputs/outputs 字段必须是列表")

        input_names: Set[str] = set()
        output_names: Set[str] = set()

        for name in inputs:
            if isinstance(name, str):
                input_names.add(name)

        for name in outputs:
            if isinstance(name, str):
                output_names.add(name)

        input_ports_by_id[node_id] = input_names
        output_ports_by_id[node_id] = output_names

    node_ids: Set[str] = set(node_by_id.keys())

    # 统计节点度数（以 edge.src_node / edge.dst_node 为依据）
    degree_by_node: Dict[str, int] = {nid: 0 for nid in node_ids}

    missing_src_nodes: List[Dict] = []
    missing_dst_nodes: List[Dict] = []
    invalid_src_ports: List[Dict] = []
    invalid_dst_ports: List[Dict] = []

    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("edges 列表中的元素必须是对象")
        edge_id = edge.get("id", "")
        src_node = edge.get("src_node")
        dst_node = edge.get("dst_node")
        src_port = edge.get("src_port")
        dst_port = edge.get("dst_port")

        if not isinstance(src_node, str) or not isinstance(dst_node, str):
            raise ValueError(f"边 {edge_id!r} 缺少 src_node/dst_node 或类型错误")
        if not isinstance(src_port, str) or not isinstance(dst_port, str):
            raise ValueError(f"边 {edge_id!r} 缺少 src_port/dst_port 或类型错误")

        # 统计度数（只对真实存在的节点做计数）
        if src_node in degree_by_node:
            degree_by_node[src_node] = degree_by_node[src_node] + 1
        if dst_node in degree_by_node:
            degree_by_node[dst_node] = degree_by_node[dst_node] + 1

        # 节点存在性检查
        src_exists = src_node in node_ids
        dst_exists = dst_node in node_ids

        if not src_exists:
            missing_src_nodes.append(
                {
                    "edge_id": edge_id,
                    "src_node": src_node,
                    "dst_node": dst_node,
                    "src_port": src_port,
                    "dst_port": dst_port,
                }
            )
        if not dst_exists:
            missing_dst_nodes.append(
                {
                    "edge_id": edge_id,
                    "src_node": src_node,
                    "dst_node": dst_node,
                    "src_port": src_port,
                    "dst_port": dst_port,
                }
            )

        # 端口名称检查（仅在对应节点存在时才检查）
        if src_exists:
            if src_port != FLOW_PORT_PLACEHOLDER:
                valid_outputs = output_ports_by_id.get(src_node, set())
                is_flow_alias = (
                    src_port in FLOW_OUT_PORT_NAMES or src_port in FLOW_BRANCH_PORT_ALIASES
                )
                if src_port not in valid_outputs and not is_flow_alias:
                    invalid_src_ports.append(
                        {
                            "edge_id": edge_id,
                            "src_node": src_node,
                            "src_port": src_port,
                            "valid_outputs": sorted(valid_outputs),
                        }
                    )

        if dst_exists:
            if dst_port != FLOW_PORT_PLACEHOLDER:
                valid_inputs = input_ports_by_id.get(dst_node, set())
                is_flow_alias = dst_port in FLOW_IN_PORT_NAMES
                if dst_port not in valid_inputs and not is_flow_alias:
                    invalid_dst_ports.append(
                        {
                            "edge_id": edge_id,
                            "dst_node": dst_node,
                            "dst_port": dst_port,
                            "valid_inputs": sorted(valid_inputs),
                        }
                    )

    # 孤立节点：在任何一条边中都未出现的节点
    orphan_nodes: List[str] = []
    for node_id, degree in degree_by_node.items():
        if degree == 0:
            orphan_nodes.append(node_id)

    has_error = bool(missing_src_nodes or missing_dst_nodes or invalid_src_ports or invalid_dst_ports)

    report = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "orphan_nodes": orphan_nodes,
        "missing_src_nodes": missing_src_nodes,
        "missing_dst_nodes": missing_dst_nodes,
        "invalid_src_ports": invalid_src_ports,
        "invalid_dst_ports": invalid_dst_ports,
    }
    return has_error, report


def validate_graph_cache_file(path: Path) -> bool:
    """
    校验单个 graph_cache 文件。

    返回：
    - True  表示存在严重结构问题；
    - False 表示未发现严重问题（但可能仍有孤立节点，仅作为提示）。
    """
    print(f"=== 检查文件: {path} ===")
    data = _load_json(path)
    graph_data = _extract_graph_data(data)
    has_error, report = _analyze_graph_data(graph_data)

    node_count = report["node_count"]
    edge_count = report["edge_count"]
    orphan_nodes: List[str] = report["orphan_nodes"]
    missing_src_nodes: List[Dict] = report["missing_src_nodes"]
    missing_dst_nodes: List[Dict] = report["missing_dst_nodes"]
    invalid_src_ports: List[Dict] = report["invalid_src_ports"]
    invalid_dst_ports: List[Dict] = report["invalid_dst_ports"]

    print(f"节点数量: {node_count}")
    print(f"边数量  : {edge_count}")

    if orphan_nodes:
        preview = ", ".join(orphan_nodes[:10])
        print(f"孤立节点: {len(orphan_nodes)} 个（示例: {preview}）")
    else:
        print("孤立节点: 0 个")

    if missing_src_nodes or missing_dst_nodes:
        print(f"幽灵节点引用: src 缺失 {len(missing_src_nodes)} 条, dst 缺失 {len(missing_dst_nodes)} 条")
        preview_edges = (missing_src_nodes + missing_dst_nodes)[:10]
        for item in preview_edges:
            edge_id = item.get("edge_id", "")
            src_node = item.get("src_node", "")
            dst_node = item.get("dst_node", "")
            print(f"  边 {edge_id}: {src_node} -> {dst_node}")
    else:
        print("幽灵节点引用: 0 条")

    if invalid_src_ports or invalid_dst_ports:
        print(
            f"端口不匹配: 源端口错误 {len(invalid_src_ports)} 条, 目标端口错误 {len(invalid_dst_ports)} 条"
        )
        preview_ports = (invalid_src_ports + invalid_dst_ports)[:10]
        for item in preview_ports:
            edge_id = item.get("edge_id", "")
            if "src_node" in item:
                src_node = item.get("src_node", "")
                src_port = item.get("src_port", "")
                print(f"  边 {edge_id}: 源端口不匹配 src_node={src_node}, src_port={src_port}")
            if "dst_node" in item:
                dst_node = item.get("dst_node", "")
                dst_port = item.get("dst_port", "")
                print(f"  边 {edge_id}: 目标端口不匹配 dst_node={dst_node}, dst_port={dst_port}")
    else:
        print("端口不匹配: 0 条")

    if has_error:
        print("结果: 存在结构错误（幽灵节点或端口名称不匹配），请修复后再使用该缓存。")
    else:
        print("结果: 未发现严重结构错误。")
    print()
    return has_error


def _iter_json_files(targets: List[Path]) -> List[Path]:
    """
    根据命令行参数收集要检查的 JSON 文件。
    - 若传入文件：直接使用；
    - 若传入目录：递归收集目录下的 *.json；
    - 若无参数：默认扫描 app/runtime/cache/graph_cache。
    """
    files: List[Path] = []

    if not targets:
        default_dir = Path("app/runtime/cache/graph_cache")
        if default_dir.is_dir():
            for p in sorted(default_dir.rglob("*.json")):
                files.append(p)
        return files

    for target in targets:
        if target.is_dir():
            for p in sorted(target.rglob("*.json")):
                files.append(p)
        elif target.is_file() and target.suffix.lower() == ".json":
            files.append(target)
    return files


def main() -> None:
    argv = sys.argv[1:]
    targets = [Path(arg) for arg in argv]
    files = _iter_json_files(targets)

    if not files:
        print("未找到任何待检查的 .json 文件。")
        sys.exit(0)

    has_any_error = False

    for path in files:
        exists = path.exists()
        if not exists:
            print(f"跳过不存在的文件: {path}")
        else:
            has_error = validate_graph_cache_file(path)
            if has_error:
                has_any_error = True

    if has_any_error:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()


