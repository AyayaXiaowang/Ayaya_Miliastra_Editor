from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.gil.graph_variable_scanner import scan_gil_file_graph_variables

from .constants import (
    CLIENT_SCOPE_MASK,
    GRAPH_ID_INT_RE,
    GRAPH_ID_LINE_RE,
    GRAPH_NAME_LINE_RE,
    GRAPH_TYPE_LINE_RE,
    SCAN_HEAD_CHARS,
    SCOPE_MASK,
    SERVER_SCOPE_MASK,
)


def _extract_graph_id_int_from_graph_key(graph_key: str) -> Optional[int]:
    m = GRAPH_ID_INT_RE.search(str(graph_key or ""))
    if not m:
        return None
    return int(m.group(1))


def _assert_scope_mask(graph_id_int: int, scope: str) -> None:
    mask = int(graph_id_int) & int(SCOPE_MASK)
    if scope == "server" and mask != SERVER_SCOPE_MASK:
        raise ValueError(f"graph_id_int mask 不属于 server：graph_id_int={graph_id_int} mask=0x{mask:X}")
    if scope == "client" and mask != CLIENT_SCOPE_MASK:
        raise ValueError(f"graph_id_int mask 不属于 client：graph_id_int={graph_id_int} mask=0x{mask:X}")


def _pick_template_graph_id_int(*, template_gil: Path, expected_scope: str) -> int:
    obs = scan_gil_file_graph_variables(Path(template_gil))
    expected_mask = SERVER_SCOPE_MASK if expected_scope == "server" else CLIENT_SCOPE_MASK

    for g in obs.graphs:
        if (int(g.graph_id_int) & int(SCOPE_MASK)) != int(expected_mask):
            continue
        if len(g.node_type_ids) <= 0:
            continue
        return int(g.graph_id_int)

    raise ValueError(
        f"未在模板 .gil 中找到可用的 template_graph_id_int（scope={expected_scope} 且包含节点样本）：{str(Path(template_gil).resolve())}"
    )


def pick_template_graph_id_int(*, template_gil: Path, expected_scope: str) -> int:
    return _pick_template_graph_id_int(template_gil=template_gil, expected_scope=expected_scope)


@dataclass(frozen=True, slots=True)
class _GraphSpec:
    scope: str  # "server" | "client"
    graph_key: str  # graph_id (Graph_Generater resource id, string)
    graph_name_hint: str
    graph_code_file: Path
    assigned_graph_id_int: int


def _reassign_compact_graph_id_ints_for_selected_specs(*, specs: Sequence[_GraphSpec]) -> List[_GraphSpec]:
    """
    对“显式选图”结果做二次 graph_id_int 规整（仅基于选中集合分配）。

    背景：
    - 选图导出时若先用全量扫描结果分配 id，单图导出可能得到很大的稀疏 id（受未选图影响）；
    - 游戏侧“仅导出一张图”通常会从 scope 起始位（server=0x40000001 / client=0x40800001）开始分配。

    规则：
    - 若 graph_key 显式携带 graph_id_int，则保留该 id（并校验 scope mask）；
    - 其余图按“选中集合内”从起始位紧凑分配，不受未选图影响；
    - 保持输入顺序（不重排 specs）。
    """
    selected_specs = list(specs or [])
    if not selected_specs:
        return []

    grouped: Dict[str, List[_GraphSpec]] = {"server": [], "client": []}
    for spec in selected_specs:
        scope = str(spec.scope or "").strip().lower()
        if scope not in {"server", "client"}:
            raise ValueError(f"unsupported scope in selected specs: {scope!r}")
        grouped[scope].append(spec)

    reserved_by_scope: Dict[str, Dict[str, int]] = {"server": {}, "client": {}}
    used_ids_by_scope: Dict[str, set[int]] = {"server": set(), "client": set()}
    next_id_by_scope: Dict[str, int] = {}

    for scope, scope_specs in grouped.items():
        reserved_map = reserved_by_scope[scope]
        used_ids = used_ids_by_scope[scope]
        for spec in scope_specs:
            reserved = _extract_graph_id_int_from_graph_key(str(spec.graph_key))
            if reserved is None:
                continue
            _assert_scope_mask(int(reserved), scope)
            existing_reserved = reserved_map.get(str(spec.graph_key))
            if existing_reserved is not None and int(existing_reserved) != int(reserved):
                raise ValueError(
                    "graph_key 保留 graph_id_int 冲突："
                    f"scope={scope!r} graph_key={spec.graph_key!r} "
                    f"a={existing_reserved} b={reserved}"
                )
            if int(reserved) in used_ids:
                raise ValueError(
                    f"selected specs 中出现重复保留 graph_id_int={int(reserved)}（scope={scope!r}）：{spec.graph_key!r}"
                )
            reserved_map[str(spec.graph_key)] = int(reserved)
            used_ids.add(int(reserved))

        scope_mask = SERVER_SCOPE_MASK if scope == "server" else CLIENT_SCOPE_MASK
        next_id_by_scope[scope] = (max(used_ids) + 1) if used_ids else (int(scope_mask) | 1)

    assigned_by_graph_key_scope: Dict[Tuple[str, str], int] = {}
    out: List[_GraphSpec] = []

    for spec in selected_specs:
        scope = str(spec.scope or "").strip().lower()
        graph_key = str(spec.graph_key)
        pair_key = (scope, graph_key)
        assigned = assigned_by_graph_key_scope.get(pair_key)
        if assigned is None:
            reserved = reserved_by_scope[scope].get(graph_key)
            if reserved is not None:
                assigned = int(reserved)
            else:
                used_ids = used_ids_by_scope[scope]
                next_id = int(next_id_by_scope[scope])
                while next_id in used_ids:
                    next_id += 1
                _assert_scope_mask(int(next_id), scope)
                assigned = int(next_id)
                used_ids.add(int(assigned))
                next_id_by_scope[scope] = int(next_id + 1)

            assigned_by_graph_key_scope[pair_key] = int(assigned)

        out.append(
            _GraphSpec(
                scope=str(spec.scope),
                graph_key=str(spec.graph_key),
                graph_name_hint=str(spec.graph_name_hint),
                graph_code_file=Path(spec.graph_code_file).resolve(),
                assigned_graph_id_int=int(assigned),
            )
        )

    return out


def _select_explicit_graph_specs(
    *,
    all_specs: Sequence[_GraphSpec],
    explicit_files: Sequence[Path],
) -> List[_GraphSpec]:
    by_file = {Path(s.graph_code_file).resolve(): s for s in list(all_specs or [])}
    normalized_explicit_files = [Path(p).resolve() for p in list(explicit_files or [])]

    missing = [str(p) for p in normalized_explicit_files if p not in by_file]
    if missing:
        raise ValueError(f"显式写回的 graph_code_files 中包含无法识别为节点图的文件（缺少 graph_id metadata）：{missing}")

    selected_specs = [by_file[p] for p in normalized_explicit_files]
    # 关键：显式选图写回按“选中集合”紧凑分配 graph_id_int，
    # 使单图导出不受未选图影响（与游戏导出行为一致）。
    return _reassign_compact_graph_id_ints_for_selected_specs(specs=selected_specs)


def _infer_scope_from_folder_key(folder_key: str) -> str:
    t = str(folder_key or "")
    if "/client" in t.replace("\\", "/"):
        return "client"
    if "/server" in t.replace("\\", "/"):
        return "server"
    raise ValueError(f"无法从 folder_key 推断 scope（期望包含 /server 或 /client）：{folder_key!r}")


def _infer_scope_from_graph_code_file(*, graph_code_file: Path, graph_type_hint: str) -> str:
    t = str(graph_type_hint or "").strip().lower()
    if t in {"server", "client"}:
        return t
    lowered = Path(graph_code_file).as_posix().lower()
    if "/client/" in lowered:
        return "client"
    if "/server/" in lowered:
        return "server"
    raise ValueError(f"无法推断节点图 scope（graph_type 缺失且路径不含 /server 或 /client）：{str(graph_code_file)}")


def _iter_graph_entries_from_overview_json(
    overview_object: Dict[str, Any],
) -> Iterable[Tuple[str, str, str, str]]:
    """
    Yields (folder_key, graph_key, file_name, graph_name_hint).
    """
    folders = overview_object.get("folders")
    if not isinstance(folders, dict):
        raise TypeError("总览 JSON 缺少 folders: dict")

    for folder_key, folder_info in folders.items():
        if not isinstance(folder_info, dict):
            continue
        graphs = folder_info.get("节点图")
        if not isinstance(graphs, dict) or not graphs:
            continue
        for graph_key, graph_info in graphs.items():
            if not isinstance(graph_info, dict):
                continue
            file_name = str(graph_info.get("file") or "").strip()
            if not file_name:
                raise ValueError(f"节点图条目缺少 file：folder={folder_key!r} graph_key={graph_key!r}")
            name = str(graph_info.get("name") or "").strip()
            yield str(folder_key), str(graph_key), file_name, name


def _build_overview_object_by_scanning_node_graph_dir(*, package_root: Path) -> Dict[str, Any]:
    """
    构造一个最小 “总览 JSON” 结构（仅包含 folders/节点图），数据源来自：

    - `<package_root>/节点图/**.py`
    - 仅收录文件头部 docstring metadata 中包含 `graph_id:` 的条目
    - 自动跳过 `_prelude.py` / `__init__.py` / 以及所有以下划线开头的辅助脚本
    """
    node_graph_root = (Path(package_root) / "节点图").resolve()
    if not node_graph_root.is_dir():
        return {"folders": {}}

    folders: Dict[str, Any] = {}
    py_files = sorted(node_graph_root.rglob("*.py"))
    for py_file in py_files:
        if py_file.name == "__init__.py":
            continue
        if py_file.name.startswith("_"):
            continue

        with py_file.open("r", encoding="utf-8") as f:
            head = f.read(SCAN_HEAD_CHARS)

        m_id = GRAPH_ID_LINE_RE.search(head)
        if not m_id:
            # 非节点图源码（例如辅助脚本）；跳过即可
            print(f"[skip] non-graph .py (missing graph_id metadata): {str(py_file)}")
            continue

        graph_id = str(m_id.group(1) or "").strip()
        if not graph_id:
            raise ValueError(f"graph_id 为空：{str(py_file)}")

        m_name = GRAPH_NAME_LINE_RE.search(head)
        graph_name = str(m_name.group(1) if m_name else "").strip() or py_file.stem

        folder_key = str(py_file.parent.relative_to(Path(package_root))).replace("\\", "/")
        graphs = folders.setdefault(folder_key, {}).setdefault("节点图", {})
        if graph_id in graphs:
            raise ValueError(f"扫描到重复 graph_id={graph_id!r}：{str(py_file)}")
        graphs[graph_id] = {"file": py_file.name, "name": graph_name}

    return {"folders": folders}


def build_overview_object_by_scanning_node_graph_dir(*, package_root: Path) -> Dict[str, Any]:
    return _build_overview_object_by_scanning_node_graph_dir(package_root=package_root)


def _build_graph_specs_by_scanning_roots(
    *,
    graph_source_roots: list[Path],
    include_server: bool,
    include_client: bool,
    strict_graph_code_files: bool,
) -> List[_GraphSpec]:
    """扫描多个资源根（project/shared）下的 节点图/**.py 并稳定分配 graph_id_int。"""
    roots = [Path(p).resolve() for p in list(graph_source_roots or [])]
    roots = [p for p in roots if p.is_dir()]
    if not roots:
        return []

    by_graph_id: Dict[str, Tuple[str, str, Path]] = {}  # graph_id -> (scope, name, file)
    for root in roots:
        node_graph_root = (Path(root) / "节点图").resolve()
        if not node_graph_root.is_dir():
            continue
        for py_file in sorted(node_graph_root.rglob("*.py"), key=lambda p: p.as_posix().casefold()):
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

            with py_file.open("r", encoding="utf-8") as f:
                head = f.read(SCAN_HEAD_CHARS)

            m_id = GRAPH_ID_LINE_RE.search(head)
            if not m_id:
                continue
            graph_id = str(m_id.group(1) or "").strip()
            if not graph_id:
                raise ValueError(f"graph_id 为空：{str(py_file)}")

            m_name = GRAPH_NAME_LINE_RE.search(head)
            graph_name = str(m_name.group(1) if m_name else "").strip() or py_file.stem
            m_type = GRAPH_TYPE_LINE_RE.search(head)
            graph_type = str(m_type.group(1) if m_type else "").strip()
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
            by_graph_id[graph_id] = (scope, graph_name, py_file.resolve())

    if not by_graph_id:
        return []

    server_entries = sorted(
        [(k, by_graph_id[k]) for k in by_graph_id.keys() if by_graph_id[k][0] == "server"],
        key=lambda pair: str(pair[0]).casefold(),
    )
    client_entries = sorted(
        [(k, by_graph_id[k]) for k in by_graph_id.keys() if by_graph_id[k][0] == "client"],
        key=lambda pair: str(pair[0]).casefold(),
    )

    def assign(scope: str, entries: List[Tuple[str, Tuple[str, str, Path]]]) -> List[_GraphSpec]:
        if not entries:
            return []
        reserved: Dict[str, int] = {}
        reserved_ids: set[int] = set()
        for graph_key, _info in entries:
            gid = _extract_graph_id_int_from_graph_key(graph_key)
            if gid is None:
                continue
            _assert_scope_mask(gid, scope)
            reserved[graph_key] = int(gid)
            if int(gid) in reserved_ids:
                raise ValueError(f"graph_key 提取到重复 graph_id_int={gid}（scope={scope}）：{graph_key!r}")
            reserved_ids.add(int(gid))

        scope_mask = SERVER_SCOPE_MASK if scope == "server" else CLIENT_SCOPE_MASK
        next_id = (max(reserved_ids) + 1) if reserved_ids else (int(scope_mask) | 1)
        assigned_ids = set(reserved_ids)

        out: List[_GraphSpec] = []
        for graph_key, info in entries:
            _scope2, name, graph_code_file = info
            if _scope2 != scope:
                raise RuntimeError("internal scope mismatch")

            assigned = reserved.get(graph_key)
            if assigned is None:
                while next_id in assigned_ids:
                    next_id += 1
                _assert_scope_mask(int(next_id), scope)
                assigned = int(next_id)
                assigned_ids.add(int(assigned))
                next_id += 1

            out.append(
                _GraphSpec(
                    scope=str(scope),
                    graph_key=str(graph_key),
                    graph_name_hint=str(name or ""),
                    graph_code_file=Path(graph_code_file).resolve(),
                    assigned_graph_id_int=int(assigned),
                )
            )
        return out

    specs: List[_GraphSpec] = []
    if include_server:
        specs.extend(assign("server", server_entries))
    if include_client:
        specs.extend(assign("client", client_entries))

    specs.sort(key=lambda s: ((0 if s.scope == "server" else 1), int(s.assigned_graph_id_int), str(s.graph_key)))
    return specs


def build_graph_specs_by_scanning_roots(
    *,
    graph_source_roots: list[Path],
    include_server: bool,
    include_client: bool,
    strict_graph_code_files: bool,
) -> List[_GraphSpec]:
    return _build_graph_specs_by_scanning_roots(
        graph_source_roots=graph_source_roots,
        include_server=include_server,
        include_client=include_client,
        strict_graph_code_files=strict_graph_code_files,
    )


def _build_graph_specs(
    *,
    package_root: Path,
    overview_object: Dict[str, Any],
    include_server: bool,
    include_client: bool,
    strict_graph_code_files: bool,
) -> List[_GraphSpec]:
    raw_entries: List[Tuple[str, str, str, str]] = list(_iter_graph_entries_from_overview_json(overview_object))
    if not raw_entries:
        return []

    server_entries: List[Tuple[str, str, str, str]] = []
    client_entries: List[Tuple[str, str, str, str]] = []
    for folder_key, graph_key, file_name, name in raw_entries:
        scope = _infer_scope_from_folder_key(folder_key)
        if scope == "server":
            server_entries.append((folder_key, graph_key, file_name, name))
        else:
            client_entries.append((folder_key, graph_key, file_name, name))

    specs: List[_GraphSpec] = []

    def assign_ids(scope: str, entries: List[Tuple[str, str, str, str]]) -> List[_GraphSpec]:
        if not entries:
            return []
        reserved: Dict[str, int] = {}
        reserved_ids: set[int] = set()
        for _folder_key, _graph_key, _file_name, _name in entries:
            gid = _extract_graph_id_int_from_graph_key(_graph_key)
            if gid is None:
                continue
            _assert_scope_mask(gid, scope)
            reserved[_graph_key] = int(gid)
            if int(gid) in reserved_ids:
                raise ValueError(f"graph_key 提取到重复 graph_id_int={gid}（scope={scope}）：{_graph_key!r}")
            reserved_ids.add(int(gid))

        scope_mask = SERVER_SCOPE_MASK if scope == "server" else CLIENT_SCOPE_MASK
        next_id = (max(reserved_ids) + 1) if reserved_ids else (int(scope_mask) | 1)
        assigned_ids = set(reserved_ids)

        out: List[_GraphSpec] = []
        for folder_key, graph_key, file_name, name in entries:
            graph_code_file = (Path(package_root) / folder_key / file_name).resolve()
            if not graph_code_file.is_file():
                if strict_graph_code_files:
                    raise FileNotFoundError(f"节点图源码不存在：{str(graph_code_file)}")
                print(f"[skip] missing graph code file: {str(graph_code_file)}")
                continue

            assigned = reserved.get(graph_key)
            if assigned is None:
                while next_id in assigned_ids:
                    next_id += 1
                _assert_scope_mask(int(next_id), scope)
                assigned = int(next_id)
                assigned_ids.add(int(assigned))
                next_id += 1

            out.append(
                _GraphSpec(
                    scope=str(scope),
                    graph_key=str(graph_key),
                    graph_name_hint=str(name or ""),
                    graph_code_file=graph_code_file,
                    assigned_graph_id_int=int(assigned),
                )
            )
        return out

    if include_server:
        specs.extend(assign_ids("server", server_entries))
    if include_client:
        specs.extend(assign_ids("client", client_entries))

    def sort_key(s: _GraphSpec) -> Tuple[int, int, str]:
        scope_rank = 0 if s.scope == "server" else 1
        return scope_rank, int(s.assigned_graph_id_int), str(s.graph_key)

    specs.sort(key=sort_key)
    return specs


def build_graph_specs(
    *,
    package_root: Path,
    overview_object: Dict[str, Any],
    include_server: bool,
    include_client: bool,
    strict_graph_code_files: bool,
) -> List[_GraphSpec]:
    return _build_graph_specs(
        package_root=package_root,
        overview_object=overview_object,
        include_server=include_server,
        include_client=include_client,
        strict_graph_code_files=strict_graph_code_files,
    )

