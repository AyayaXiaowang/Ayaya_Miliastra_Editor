from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _infer_resource_class_from_graph_code_file(*, graph_code_file: Path, scope: str) -> str:
    """
    将项目存档内的“节点图目录结构”映射到 NodeEditorPack `ResourceEntry.ResourceClass`：

    - server/实体节点图 → ENTITY_NODE_GRAPH
    - server/状态节点图 → STATUS_NODE_GRAPH
    - server/职业节点图 → CLASS_NODE_GRAPH
    - server/道具节点图 → ITEM_NODE_GRAPH
    - client/布尔过滤器节点图 → BOOLEAN_FILTER_GRAPH
    - client/整数过滤器节点图 → INTEGER_FILTER_GRAPH
    - client/技能节点图 → SKILL_NODE_GRAPH
    """
    p = Path(graph_code_file)
    parts = [str(x) for x in p.parts]
    scope_norm = str(scope or "").strip().lower()

    # 不使用 try/except：缺失时按 scope 兜底
    if "节点图" not in parts:
        return "ENTITY_NODE_GRAPH" if scope_norm != "client" else "BOOLEAN_FILTER_GRAPH"
    idx = int(parts.index("节点图"))

    if idx + 2 >= len(parts):
        return "ENTITY_NODE_GRAPH" if scope_norm != "client" else "BOOLEAN_FILTER_GRAPH"

    # 约定：.../节点图/{server|client}/{子类目录}/...
    kind = str(parts[idx + 2] or "").strip()
    if scope_norm == "server":
        mapping = {
            "实体节点图": "ENTITY_NODE_GRAPH",
            "状态节点图": "STATUS_NODE_GRAPH",
            "职业节点图": "CLASS_NODE_GRAPH",
            "道具节点图": "ITEM_NODE_GRAPH",
        }
        return str(mapping.get(kind, "ENTITY_NODE_GRAPH"))

    mapping2 = {
        "布尔过滤器节点图": "BOOLEAN_FILTER_GRAPH",
        "整数过滤器节点图": "INTEGER_FILTER_GRAPH",
        "技能节点图": "SKILL_NODE_GRAPH",
    }
    return str(mapping2.get(kind, "BOOLEAN_FILTER_GRAPH"))


def _scan_graph_head_metadata(graph_code_file: Path) -> tuple[str, str, str]:
    """读取 Graph Code 头部 docstring metadata：返回 (graph_id, graph_name, graph_type)。"""
    head = Path(graph_code_file).read_text(encoding="utf-8", errors="strict")[:8192]
    graph_id = ""
    graph_name = ""
    graph_type = ""

    for line in str(head).splitlines():
        stripped = str(line or "").strip()
        lowered = stripped.lower()
        if lowered.startswith("graph_id:"):
            graph_id = stripped[len("graph_id:") :].strip()
            continue
        if lowered.startswith("graph_name:"):
            graph_name = stripped[len("graph_name:") :].strip()
            continue
        if lowered.startswith("graph_type:"):
            graph_type = stripped[len("graph_type:") :].strip()
            continue

    return str(graph_id or "").strip(), str(graph_name or "").strip(), str(graph_type or "").strip()


def _infer_scope_from_graph_code_file(*, graph_code_file: Path, graph_type_hint: str) -> str:
    """推断 scope：优先用 metadata.graph_type，其次从路径包含 server/client 推断。"""
    t = str(graph_type_hint or "").strip().lower()
    if t in {"server", "client"}:
        return t
    p = Path(graph_code_file)
    lowered = p.as_posix().lower()
    if "/client/" in lowered:
        return "client"
    if "/server/" in lowered:
        return "server"
    raise ValueError(f"无法推断节点图 scope（graph_type 缺失且路径不含 /server 或 /client）：{str(p)}")


@dataclass(frozen=True, slots=True)
class _GraphExportSpec:
    scope: str  # "server" | "client"
    graph_key: str  # graph_id
    graph_name_hint: str
    graph_code_file: Path
    assigned_graph_id_int: int


def _extract_graph_id_int_from_graph_key(graph_key: str) -> int | None:
    # 复用 node_graphs_importer 的编码约定：graph_key 中若包含 `_1073741825__` 形式，提取为保留 id。
    import re

    m = re.search(r"_(\d{10})(?:__|$)", str(graph_key or ""))
    if not m:
        return None
    return int(m.group(1))


def _assert_scope_mask(graph_id_int: int, scope: str) -> None:
    # 与 node_graphs_importer 保持一致
    SERVER_SCOPE_MASK = 0x40000000
    CLIENT_SCOPE_MASK = 0x40800000
    SCOPE_MASK = 0xFF800000
    mask = int(graph_id_int) & int(SCOPE_MASK)
    if scope == "server" and mask != SERVER_SCOPE_MASK:
        raise ValueError(f"graph_id_int mask 不属于 server：graph_id_int={graph_id_int} mask=0x{mask:X}")
    if scope == "client" and mask != CLIENT_SCOPE_MASK:
        raise ValueError(f"graph_id_int mask 不属于 client：graph_id_int={graph_id_int} mask=0x{mask:X}")


def _build_graph_specs_by_scanning_roots(
    *,
    graph_source_roots: list[Path],
    include_server: bool,
    include_client: bool,
    strict_graph_code_files: bool,
) -> list[_GraphExportSpec]:
    """扫描多个资源根（project/shared）下的 节点图/**.py 并稳定分配 graph_id_int。"""
    roots = [Path(p).resolve() for p in list(graph_source_roots or [])]
    roots = [p for p in roots if p.is_dir()]
    if not roots:
        return []

    # graph_id -> (scope, name, file_path)
    by_graph_id: dict[str, tuple[str, str, Path]] = {}

    for root in roots:
        node_graph_root = (root / "节点图").resolve()
        if not node_graph_root.is_dir():
            continue
        for py_file in sorted(node_graph_root.rglob("*.py"), key=lambda x: x.as_posix().casefold()):
            if py_file.name == "__init__.py":
                continue
            if py_file.name.startswith("_"):
                continue
            if "校验" in py_file.stem:
                continue
            if not py_file.is_file():
                continue

            if strict_graph_code_files and not py_file.exists():
                raise FileNotFoundError(str(py_file))

            graph_id, graph_name, graph_type = _scan_graph_head_metadata(py_file)
            if not graph_id:
                continue
            scope = _infer_scope_from_graph_code_file(graph_code_file=py_file, graph_type_hint=graph_type)
            if scope == "server" and not include_server:
                continue
            if scope == "client" and not include_client:
                continue

            existing = by_graph_id.get(graph_id)
            if existing is not None:
                _, _, old_path = existing
                raise ValueError(
                    "扫描到重复 graph_id（project/shared 或多根冲突）：\n"
                    f"- graph_id: {graph_id}\n"
                    f"- a: {str(old_path)}\n"
                    f"- b: {str(py_file)}"
                )
            by_graph_id[graph_id] = (scope, graph_name or py_file.stem, py_file.resolve())

    if not by_graph_id:
        return []

    # 先按 scope 拆分并稳定排序（按 graph_id）
    server_keys = sorted([k for k, (s, _n, _p) in by_graph_id.items() if s == "server"], key=lambda t: t.casefold())
    client_keys = sorted([k for k, (s, _n, _p) in by_graph_id.items() if s == "client"], key=lambda t: t.casefold())

    def _assign(scope: str, keys: list[str]) -> list[_GraphExportSpec]:
        if not keys:
            return []
        reserved: dict[str, int] = {}
        reserved_ids: set[int] = set()
        for graph_key in keys:
            gid = _extract_graph_id_int_from_graph_key(graph_key)
            if gid is None:
                continue
            _assert_scope_mask(int(gid), scope)
            reserved[graph_key] = int(gid)
            if int(gid) in reserved_ids:
                raise ValueError(f"graph_key 提取到重复 graph_id_int={gid}（scope={scope}）：{graph_key!r}")
            reserved_ids.add(int(gid))

        scope_mask = 0x40000000 if scope == "server" else 0x40800000
        next_id = (max(reserved_ids) + 1) if reserved_ids else (int(scope_mask) | 1)
        assigned_ids = set(reserved_ids)

        specs: list[_GraphExportSpec] = []
        for graph_key in keys:
            scope2, name, file_path = by_graph_id[graph_key]
            if scope2 != scope:
                raise RuntimeError("internal scope mismatch")

            assigned = reserved.get(graph_key)
            if assigned is None:
                while next_id in assigned_ids:
                    next_id += 1
                _assert_scope_mask(int(next_id), scope)
                assigned = int(next_id)
                assigned_ids.add(int(assigned))
                next_id += 1

            specs.append(
                _GraphExportSpec(
                    scope=str(scope),
                    graph_key=str(graph_key),
                    graph_name_hint=str(name or ""),
                    graph_code_file=Path(file_path).resolve(),
                    assigned_graph_id_int=int(assigned),
                )
            )
        return specs

    out: list[_GraphExportSpec] = []
    if include_server:
        out.extend(_assign("server", server_keys))
    if include_client:
        out.extend(_assign("client", client_keys))

    out.sort(key=lambda s: (0 if s.scope == "server" else 1, int(s.assigned_graph_id_int), str(s.graph_key)))
    return out

