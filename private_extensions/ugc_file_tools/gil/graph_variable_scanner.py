from __future__ import annotations

"""
gil_graph_variable_scanner.py

用途：
- 不依赖 DLL，直接解析 `.gil` 的 payload（protobuf-like），扫描节点图 GraphEntry['6']（节点图变量定义表）。
- 该扫描器用于：
  - 真源样本差异分析（对齐 Graph_Generater type_registry）
  - 写回产物合约校验（确保我们写回的节点图变量表满足约束）

约束：
- 不使用 try/except；错误直接抛出，便于定位样本/格式差异。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_package_exporter.gil_reader import read_gil_header


def read_payload_bytes_from_gil(gil_path: Path) -> bytes:
    file_bytes = Path(gil_path).read_bytes()
    header = read_gil_header(file_bytes)
    body_size = int(header.body_size)
    if body_size <= 0:
        raise ValueError(f"invalid gil body_size={body_size}: {str(gil_path)!r}")
    payload = file_bytes[20 : 20 + body_size]
    if len(payload) != body_size:
        raise ValueError(f"payload size mismatch: expected={body_size} got={len(payload)} path={str(gil_path)!r}")
    return payload


def as_message_list(node: Any) -> List[Dict[str, Any]]:
    """将 decode_bytes_to_python 的 repeated 形态（单元素 dict / 多元素 list）统一为 message dict 列表。"""
    if node is None:
        return []
    if isinstance(node, list):
        out: List[Dict[str, Any]] = []
        for item in node:
            if not isinstance(item, dict):
                continue
            msg = item.get("message")
            if isinstance(msg, dict):
                out.append(msg)
            else:
                out.append(item)
        return out
    if isinstance(node, dict):
        msg = node.get("message")
        if isinstance(msg, dict):
            return [msg]
        return [node]
    return []


def extract_int(node: Any) -> Optional[int]:
    if isinstance(node, int):
        return int(node)
    if isinstance(node, dict):
        number = node.get("int")
        if isinstance(number, int):
            return int(number)
    return None


def extract_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        text = node.get("utf8")
        if isinstance(text, str):
            return text
    return ""


@dataclass(frozen=True, slots=True)
class GraphVariableObserved:
    name: str
    var_type_int: int
    key_type_int: int
    value_type_int: int


@dataclass(frozen=True, slots=True)
class GraphEntryObserved:
    graph_id_int: int
    graph_name: str
    variables: Tuple[GraphVariableObserved, ...]
    node_type_ids: Tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class FileObserved:
    gil_path: str
    graphs: Tuple[GraphEntryObserved, ...]


def iter_gil_files_from_paths(paths: Sequence[str]) -> List[Path]:
    results: List[Path] = []
    for raw in paths:
        p = Path(raw).resolve()
        if p.is_file():
            if p.suffix.lower() == ".gil":
                results.append(p)
            continue
        if p.is_dir():
            for f in sorted(p.rglob("*.gil")):
                if f.is_file():
                    results.append(f.resolve())
            continue
        raise FileNotFoundError(str(p))

    # 去重保持稳定顺序
    seen: Set[str] = set()
    unique: List[Path] = []
    for p in results:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def scan_gil_file_graph_variables(gil_path: Path) -> FileObserved:
    payload = read_payload_bytes_from_gil(gil_path)
    decoded = decode_bytes_to_python(payload)
    if not isinstance(decoded, dict):
        raise ValueError("decoded payload is not dict")

    section10 = decoded.get("field_10")
    if not isinstance(section10, dict):
        return FileObserved(gil_path=str(gil_path), graphs=tuple())
    section10_msg = section10.get("message")
    if not isinstance(section10_msg, dict):
        return FileObserved(gil_path=str(gil_path), graphs=tuple())

    graphs: List[GraphEntryObserved] = []

    groups = as_message_list(section10_msg.get("field_1"))
    for group_msg in groups:
        entries = as_message_list(group_msg.get("field_1"))
        for entry_msg in entries:
            header_msg_list = as_message_list(entry_msg.get("field_1"))
            header_msg = header_msg_list[0] if header_msg_list else {}
            graph_id_int = extract_int(header_msg.get("field_5"))
            if not isinstance(graph_id_int, int):
                continue
            graph_name = extract_text(entry_msg.get("field_2"))

            # nodes：entry['3']，用于统计模板库中已覆盖的 node type_id
            nodes_msgs = as_message_list(entry_msg.get("field_3"))
            node_type_ids: List[int] = []
            for node_msg in nodes_msgs:
                # type_id 通常在 node.field_2.message.field_5.int（与 DLL dump-json 的 node['2'] 一致）
                m2 = node_msg.get("field_2")
                m2_msg = m2.get("message") if isinstance(m2, dict) else None
                tid = extract_int(m2_msg.get("field_5") if isinstance(m2_msg, dict) else None)
                if tid is None:
                    # fallback：有些样本可能在 field_3 上也能取到
                    m3 = node_msg.get("field_3")
                    m3_msg = m3.get("message") if isinstance(m3, dict) else None
                    tid = extract_int(m3_msg.get("field_5") if isinstance(m3_msg, dict) else None)
                if isinstance(tid, int):
                    node_type_ids.append(int(tid))

            variables_msgs = as_message_list(entry_msg.get("field_6"))
            variables: List[GraphVariableObserved] = []
            for var_msg in variables_msgs:
                var_name = extract_text(var_msg.get("field_2"))
                var_type_int = extract_int(var_msg.get("field_3"))
                if not isinstance(var_type_int, int):
                    continue
                key_type_int = extract_int(var_msg.get("field_7"))
                value_type_int = extract_int(var_msg.get("field_8"))
                variables.append(
                    GraphVariableObserved(
                        name=str(var_name),
                        var_type_int=int(var_type_int),
                        key_type_int=int(key_type_int) if isinstance(key_type_int, int) else -1,
                        value_type_int=int(value_type_int) if isinstance(value_type_int, int) else -1,
                    )
                )

            graphs.append(
                GraphEntryObserved(
                    graph_id_int=int(graph_id_int),
                    graph_name=str(graph_name),
                    variables=tuple(variables),
                    node_type_ids=tuple(node_type_ids),
                )
            )

    return FileObserved(gil_path=str(gil_path), graphs=tuple(graphs))


def collect_node_type_ids_from_gil(gil_path: Path) -> Set[int]:
    """扫描一个 `.gil` 的所有节点图，返回其中出现过的 node type_id_int 集合（不依赖 DLL）。"""
    obs = scan_gil_file_graph_variables(gil_path)
    out: Set[int] = set()
    for g in obs.graphs:
        for tid in g.node_type_ids:
            out.add(int(tid))
    return out


def collect_node_type_ids_from_gil_graph(*, gil_path: Path, graph_id_int: int) -> Set[int]:
    """扫描一个 `.gil` 的指定 graph_id_int，返回该图内出现过的 node type_id_int 集合。"""
    obs = scan_gil_file_graph_variables(gil_path)
    for g in obs.graphs:
        if int(g.graph_id_int) == int(graph_id_int):
            return {int(t) for t in g.node_type_ids}
    raise ValueError(f"未在 .gil 中找到 graph_id_int={int(graph_id_int)}：{str(Path(gil_path).resolve())}")


