from __future__ import annotations

"""
write_graph_generater_package_test2_graphs_to_gil.py

目标：
- 读取 Graph_Generater 项目存档（默认 package_id=test2）的“总览索引”（<package>总览.json），定位其中声明的节点图源码（Graph Code, .py）；
- 对每张图执行：
  - Graph_Generater：Graph Code → GraphModel(JSON, 含自动布局 + 端口类型)
  - ugc_file_tools：GraphModel(JSON) → 写回到 `.gil` 节点图段（payload field 10）
- 将所有图批量写入同一个输出 `.gil`（server/client 混合，按 scope 选择不同模板库）。

说明：
- 不使用 try/except；失败直接抛错，便于定位缺口（mapping/template/node_def 等）。
- 默认仅覆盖“总览索引里声明的节点图”（通常是 package 的稳定入口图 + 校准图），而不是扫描目录下所有 .py。
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# 兼容：允许以脚本方式运行 `python ugc_file_tools/write_graph_generater_package_test2_graphs_to_gil.py ...`
# 此时 sys.path 默认不包含仓库根目录，导致 `import ugc_file_tools.*` 失败。
if __package__ is None:
    # ugc_file_tools/commands/<tool>.py -> repo root
    workspace_root = Path(__file__).resolve().parents[2]
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))

from ugc_file_tools.graph.port_types import enrich_graph_model_with_port_types, load_node_defs_by_name_from_registry
from ugc_file_tools.gil.graph_variable_scanner import scan_gil_file_graph_variables
from ugc_file_tools.node_graph_writeback.writer import write_graph_model_to_gil
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.project_archive_importer.signals_importer import SignalsImportOptions, import_signals_from_project_archive_to_gil
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root


SERVER_SCOPE_MASK = 0x40000000
CLIENT_SCOPE_MASK = 0x40800000
SCOPE_MASK = 0xFF800000

# GraphEntry.graph_id_int（server/client）通常为 10 位十进制（包含 scope mask: 0x40000000/0x40800000）。
# 注意：Graph_Generater 的校准图 graph_id 里可能包含 `_001__test2` 这类“分片编号”，不能当作 graph_id_int。
_GRAPH_ID_INT_RE = re.compile(r"_(\d{10})(?:__|$)")

# 扫描 Graph Code 文件头部（docstring metadata）用：避免把 `_prelude.py` 等辅助脚本当作节点图。
_SCAN_HEAD_CHARS = 8192
_GRAPH_ID_LINE_RE = re.compile(r"(?m)^\s*graph_id\s*:\s*(\S+)\s*$")
_GRAPH_NAME_LINE_RE = re.compile(r"(?m)^\s*graph_name\s*:\s*(.+?)\s*$")


@dataclass(frozen=True, slots=True)
class _GraphSpec:
    scope: str  # "server" | "client"
    graph_key: str  # graph_id (Graph_Generater resource id, string)
    graph_name_hint: str
    graph_code_file: Path
    assigned_graph_id_int: int


@dataclass(frozen=True, slots=True)
class _GGContext:
    gg_root: Path
    workspace_root: Path
    package_id: str
    ResourceType: Any
    resource_manager: Any
    cache_manager: Any
    GraphModel: Any
    load_graph_metadata_from_file: Any
    node_defs_by_scope: Dict[str, Dict[str, Any]]


def _prepare_graph_generater_context(*, gg_root: Path, package_id: str) -> _GGContext:
    root = Path(gg_root).resolve()
    if not (root / "engine").is_dir():
        raise FileNotFoundError(f"invalid Graph_Generater root (missing engine/): {str(root)!r}")
    if not (root / "app").is_dir():
        raise FileNotFoundError(f"invalid Graph_Generater root (missing app/): {str(root)!r}")

    # 让 ugc_file_tools 侧可直接 import Graph_Generater 的 engine/app（只加 root 与 assets）
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(root / "assets") not in sys.path:
        sys.path.insert(1, str(root / "assets"))

    ensure_settings_workspace_root = getattr(import_module("engine.utils.workspace"), "ensure_settings_workspace_root")
    workspace_root = Path(
        ensure_settings_workspace_root(
            explicit_root=root,
            start_paths=[root],
            load_user_settings=True,
        )
    ).resolve()

    ResourceType = getattr(import_module("engine.configs.resource_types"), "ResourceType")
    ResourceManager = getattr(import_module("engine.resources.resource_manager"), "ResourceManager")
    PersistentGraphCacheManager = getattr(
        import_module("engine.resources.persistent_graph_cache_manager"), "PersistentGraphCacheManager"
    )
    GraphModel = getattr(import_module("engine.graph.models.graph_model"), "GraphModel")
    load_graph_metadata_from_file = getattr(import_module("engine.graph.utils.metadata_extractor"), "load_graph_metadata_from_file")

    resource_manager = ResourceManager(Path(workspace_root))
    resource_manager.set_active_package_id(str(package_id) or None)
    # 仅构建一次索引，避免每个图都触发 resource_index.json 的落盘与潜在锁冲突
    resource_manager.rebuild_index()

    cache_manager = PersistentGraphCacheManager(Path(workspace_root))

    node_defs_by_scope = {
        "server": load_node_defs_by_name_from_registry(workspace_root=Path(workspace_root), scope="server"),
        "client": load_node_defs_by_name_from_registry(workspace_root=Path(workspace_root), scope="client"),
    }

    return _GGContext(
        gg_root=Path(root),
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        ResourceType=ResourceType,
        resource_manager=resource_manager,
        cache_manager=cache_manager,
        GraphModel=GraphModel,
        load_graph_metadata_from_file=load_graph_metadata_from_file,
        node_defs_by_scope=node_defs_by_scope,
    )


def _export_graph_model_json_from_graph_code_with_context(
    *,
    ctx: _GGContext,
    graph_code_file: Path,
    output_json_file: Path,
) -> Dict[str, Any]:
    code_path = Path(graph_code_file).resolve()
    if not code_path.is_file():
        raise FileNotFoundError(str(code_path))

    graph_meta = ctx.load_graph_metadata_from_file(code_path)
    graph_id = str(getattr(graph_meta, "graph_id", "") or "").strip()
    if not graph_id:
        raise ValueError(f"节点图源码未声明 graph_id（docstring metadata）：{str(code_path)!r}")

    # 解析并确保 graph_cache 生成（不重建索引）
    ctx.resource_manager.invalidate_graph_for_reparse(graph_id)
    loaded = ctx.resource_manager.load_resource(ctx.ResourceType.GRAPH, graph_id)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"加载节点图失败或不在当前作用域索引中：graph_id={graph_id!r}")

    result_data = ctx.cache_manager.read_persistent_graph_cache_result_data(graph_id)
    if not isinstance(result_data, dict):
        raise RuntimeError(f"未生成持久化 graph_cache result_data：graph_id={graph_id!r}")

    graph_model_payload = result_data.get("data")
    if not isinstance(graph_model_payload, dict):
        raise TypeError("graph_cache result_data['data'] must be dict")

    graph_model = ctx.GraphModel.deserialize(graph_model_payload)
    graph_scope = str(result_data.get("graph_type") or (graph_model_payload.get("metadata") or {}).get("graph_type") or "server")
    node_defs_by_name = ctx.node_defs_by_scope.get(str(graph_scope), ctx.node_defs_by_scope["server"])
    _enrich_graph_model_with_port_types(
        graph_model=graph_model,
        graph_model_payload=graph_model_payload,
        node_defs_by_name=node_defs_by_name,
    )

    output_payload = dict(result_data)
    output_payload["graph_code_file"] = str(code_path)
    output_payload["graph_generater_root"] = str(ctx.gg_root)
    output_payload["active_package_id"] = str(ctx.package_id or "")

    output_path = resolve_output_file_path_in_out_dir(Path(output_json_file))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "graph_code_file": str(code_path),
        "output_json": str(output_path),
        "graph_name": str(result_data.get("name") or ""),
        "graph_id": str(graph_id),
        "active_package_id": str(ctx.package_id or ""),
        "nodes_count": len(getattr(graph_model, "nodes", {}) or {}),
        "edges_count": len(getattr(graph_model, "edges", {}) or {}),
    }


def _infer_scope_from_folder_key(folder_key: str) -> str:
    t = str(folder_key or "")
    if "/client" in t.replace("\\", "/"):
        return "client"
    if "/server" in t.replace("\\", "/"):
        return "server"
    raise ValueError(f"无法从 folder_key 推断 scope（期望包含 /server 或 /client）：{folder_key!r}")


def _extract_graph_id_int_from_graph_key(graph_key: str) -> Optional[int]:
    m = _GRAPH_ID_INT_RE.search(str(graph_key or ""))
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
        raise FileNotFoundError(f"节点图目录不存在：{str(node_graph_root)}")

    folders: Dict[str, Any] = {}
    py_files = sorted(node_graph_root.rglob("*.py"))
    for py_file in py_files:
        if py_file.name == "__init__.py":
            continue
        if py_file.name.startswith("_"):
            continue

        with py_file.open("r", encoding="utf-8") as f:
            head = f.read(_SCAN_HEAD_CHARS)

        m_id = _GRAPH_ID_LINE_RE.search(head)
        if not m_id:
            # 非节点图源码（例如辅助脚本）；跳过即可
            print(f"[skip] non-graph .py (missing graph_id metadata): {str(py_file)}")
            continue

        graph_id = str(m_id.group(1) or "").strip()
        if not graph_id:
            raise ValueError(f"graph_id 为空：{str(py_file)}")

        m_name = _GRAPH_NAME_LINE_RE.search(head)
        graph_name = str(m_name.group(1) if m_name else "").strip() or py_file.stem

        folder_key = str(py_file.parent.relative_to(Path(package_root))).replace("\\", "/")
        graphs = folders.setdefault(folder_key, {}).setdefault("节点图", {})
        if graph_id in graphs:
            raise ValueError(f"扫描到重复 graph_id={graph_id!r}：{str(py_file)}")
        graphs[graph_id] = {"file": py_file.name, "name": graph_name}

    return {"folders": folders}


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
        raise ValueError("总览 JSON 未包含任何 节点图 条目")

    # 先按 scope 分桶，提取“显式 graph_id_int”（从 graph_key 中提取）
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
                # 容错：总览索引可能包含“已移除/未提交”的文件条目；默认跳过并继续
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

    # 稳定排序：先 scope，再 graph_id_int
    def sort_key(s: _GraphSpec) -> Tuple[int, int, str]:
        scope_rank = 0 if s.scope == "server" else 1
        return scope_rank, int(s.assigned_graph_id_int), str(s.graph_key)

    specs.sort(key=sort_key)
    return specs


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="将 Graph_Generater 项目存档（默认 test2）中“总览索引声明的节点图”批量写回到一个 .gil 文件。"
    )
    parser.add_argument(
        "--graph-generater-root",
        default=str(repo_root()),
        help="Graph_Generater 根目录（默认 workspace/Graph_Generater）",
    )
    parser.add_argument("--package-id", default="test2", help="项目存档 package_id（默认 test2）")
    parser.add_argument(
        "--overview-json",
        default=None,
        help="可选：<package>总览.json 路径（默认自动推断为 Graph_Generater/assets/资源库/项目存档/<package>/<package>总览.json）",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="扫描项目存档 `<package>/节点图/**.py` 并收录所有带 `graph_id:` metadata 的节点图源码；开启后忽略 --overview-json。",
    )
    parser.add_argument(
        "--scope",
        choices=["all", "server", "client"],
        default="all",
        help="写回范围：all/server/client（默认 all）",
    )
    parser.add_argument(
        "--base-gil",
        default=str(
            ugc_file_tools_root()
            / "builtin_resources"
            / "empty_base_samples"
            / "empty_base_with_infra.gil"
        ),
        help=(
            "base 容器 .gil（通常为“带基础设施的空存档”；默认 "
            "ugc_file_tools/builtin_resources/empty_base_samples/empty_base_with_infra.gil）"
        ),
    )
    parser.add_argument(
        "--server-template-gil",
        default=str(
            ugc_file_tools_root()
            / "builtin_resources"
            / "template_library"
            / "test2_server_writeback_samples"
            / "autowire_templates_test2_server_direct_export_v2.gil"
        ),
        help="server 写回模板 .gil（提供节点/record 样本与节点图段结构模板）",
    )
    parser.add_argument(
        "--server-template-library-dir",
        default=str(
            ugc_file_tools_root() / "builtin_resources" / "template_library" / "test2_server_writeback_samples"
        ),
        help="server 额外模板样本库目录（递归扫描 *.gil）",
    )
    parser.add_argument(
        "--client-template-gil",
        default=str(
            ugc_file_tools_root()
            / "builtin_resources"
            / "template_library"
            / "test2_client_writeback_samples"
            / "missing_nodes_wall_test2_client_autowired.gil"
        ),
        help="client 写回模板 .gil（提供节点/record 样本与节点图段结构模板）",
    )
    parser.add_argument(
        "--client-template-library-dir",
        default=str(
            ugc_file_tools_root() / "builtin_resources" / "template_library" / "test2_client_writeback_samples"
        ),
        help="client 额外模板样本库目录（递归扫描 *.gil）",
    )
    parser.add_argument(
        "--mapping-json",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="typeId→节点名映射（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    parser.add_argument(
        "--output-gil",
        default="test2_all_graphs.writeback.gil",
        help="输出 .gil（强制写入 ugc_file_tools/out/）",
    )
    parser.add_argument(
        "--output-model-dir",
        default="test2_graph_models",
        help="GraphModel JSON 输出目录（强制写入 ugc_file_tools/out/<dir>/）",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：若总览索引引用的节点图源码文件缺失则直接报错（默认会跳过缺失条目）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    gg_root = Path(args.graph_generater_root).resolve()
    package_id = str(args.package_id).strip()
    if not package_id:
        raise ValueError("--package-id 不能为空")

    package_root = (gg_root / "assets" / "资源库" / "项目存档" / package_id).resolve()
    if not package_root.is_dir():
        raise FileNotFoundError(f"package_root 不存在：{str(package_root)}")

    if bool(args.scan_all):
        overview_object = _build_overview_object_by_scanning_node_graph_dir(package_root=package_root)
    else:
        overview_json = Path(args.overview_json).resolve() if args.overview_json else (package_root / f"{package_id}总览.json")
        if not overview_json.is_file():
            raise FileNotFoundError(f"overview_json 不存在：{str(overview_json)}")

        overview_object = json.loads(overview_json.read_text(encoding="utf-8"))
        if not isinstance(overview_object, dict):
            raise TypeError("overview_json must be dict")

    scope_text = str(args.scope)
    include_server = scope_text in ("all", "server")
    include_client = scope_text in ("all", "client")

    specs = _build_graph_specs(
        package_root=package_root,
        overview_object=overview_object,
        include_server=bool(include_server),
        include_client=bool(include_client),
        strict_graph_code_files=bool(args.strict),
    )
    if not specs:
        raise ValueError("未选中任何节点图")

    base_gil = Path(args.base_gil).resolve()
    if not base_gil.is_file():
        raise FileNotFoundError(str(base_gil))

    server_template_gil = Path(args.server_template_gil).resolve()
    client_template_gil = Path(args.client_template_gil).resolve()
    server_template_library_dir = Path(args.server_template_library_dir).resolve()
    client_template_library_dir = Path(args.client_template_library_dir).resolve()

    if include_server and not server_template_gil.is_file():
        raise FileNotFoundError(str(server_template_gil))
    if include_client and not client_template_gil.is_file():
        raise FileNotFoundError(str(client_template_gil))

    mapping_json = Path(args.mapping_json).resolve()
    if not mapping_json.is_file():
        raise FileNotFoundError(str(mapping_json))

    output_gil = resolve_output_file_path_in_out_dir(Path(args.output_gil))
    model_dir = resolve_output_file_path_in_out_dir(Path(args.output_model_dir) / "_dummy.json").parent
    model_dir.mkdir(parents=True, exist_ok=True)

    gg_ctx = _prepare_graph_generater_context(gg_root=gg_root, package_id=str(package_id))

    server_template_graph_id_int = (
        _pick_template_graph_id_int(template_gil=server_template_gil, expected_scope="server") if include_server else -1
    )
    client_template_graph_id_int = (
        _pick_template_graph_id_int(template_gil=client_template_gil, expected_scope="client") if include_client else -1
    )

    # 先写回信号定义（覆盖“空存档 + 仅节点图导出”场景，保证 signal node_def 已存在）。
    signal_step_report = import_signals_from_project_archive_to_gil(
        project_archive_path=package_root,
        input_gil_file_path=base_gil,
        output_gil_file_path=output_gil,
        template_gil_file_path=None,
        bootstrap_template_gil_file_path=None,
        options=SignalsImportOptions(
            param_build_mode="semantic",
            include_signal_ids=None,
            duplicate_name_policy="keep_first",
        ),
    )

    # 逐图导出 GraphModel + 写回（每张图写入后，下一张图以上一轮输出作为 base，确保累积）
    current_base = output_gil if output_gil.is_file() else base_gil
    reports: List[Dict[str, Any]] = []

    for spec in specs:
        scope = str(spec.scope)
        template_gil = server_template_gil if scope == "server" else client_template_gil
        template_library_dir = server_template_library_dir if scope == "server" else client_template_library_dir
        template_graph_id_int = server_template_graph_id_int if scope == "server" else client_template_graph_id_int

        # 1) Graph_Generater：Graph Code → GraphModel(JSON,含 layout + port types)
        model_out = model_dir / scope / f"{spec.graph_key}.graph_model.typed.json"
        model_out.parent.mkdir(parents=True, exist_ok=True)
        export_report = _export_graph_model_json_from_graph_code_with_context(
            ctx=gg_ctx,
            graph_code_file=Path(spec.graph_code_file),
            output_json_file=Path(model_out),
        )
        graph_model_json_path = Path(str(export_report["output_json"])).resolve()

        # 2) ugc_file_tools：GraphModel(JSON) → 写回 GIL
        write_report = write_graph_model_to_gil(
            graph_model_json_path=graph_model_json_path,
            template_gil_path=template_gil,
            base_gil_path=current_base,
            template_library_dir=template_library_dir,
            output_gil_path=output_gil,
            template_graph_id_int=int(template_graph_id_int),
            new_graph_name=str(export_report.get("graph_name") or spec.graph_name_hint or spec.graph_key),
            new_graph_id_int=int(spec.assigned_graph_id_int),
            mapping_path=mapping_json,
            graph_generater_root=gg_root,
        )

        reports.append(
            {
                "scope": scope,
                "graph_key": spec.graph_key,
                "graph_code_file": str(spec.graph_code_file),
                "graph_name": str(export_report.get("graph_name") or ""),
                "graph_model_json": str(graph_model_json_path),
                "written_graph_id_int": int(spec.assigned_graph_id_int),
                "write_report": dict(write_report),
            }
        )
        current_base = output_gil

    summary_path = resolve_output_file_path_in_out_dir(model_dir / "writeback_summary.json")
    summary_path.write_text(
        json.dumps(
            {
                "signals_writeback": signal_step_report,
                "node_graphs_writeback": reports,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 80)
    print("批量写回完成：")
    print(f"- package_id: {package_id}")
    print(
        "- signals_written: "
        f"{len(list(signal_step_report.get('added_signals') or [])) if isinstance(signal_step_report, dict) else 0}"
    )
    print(f"- graphs_written: {len(reports)}")
    print(f"- output_gil: {str(output_gil)}")
    print(f"- summary: {str(summary_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()


