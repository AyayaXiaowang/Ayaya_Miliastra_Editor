from __future__ import annotations

import ast
import io
import json
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from engine.utils.graph.node_defs_fingerprint import compute_node_defs_fingerprint
from engine.utils.path_utils import normalize_slash
from engine.utils.source_text import read_source_text
from engine.utils.resource_library_layout import discover_scoped_resource_root_directories
from engine.graph.utils.metadata_extractor import extract_metadata_from_docstring

from ugc_file_tools.node_graph_semantics.signal_usage import collect_signal_name_counts_from_graph_model_payload


INDEX_VERSION_V1: str = "analysis_usage_index_v1"
GRAPH_CODE_EXTENSION: str = ".py"
GRAPH_CACHE_DATA_KEY: str = "data"
DEFAULT_GRAPH_TYPE: str = "server"
GRAPH_CACHE_MEMORY_MAX_SIZE: int = 64

GRAPH_DIRNAME: str = "节点图"
GRAPH_TYPE_SERVER: str = "server"
GRAPH_TYPE_CLIENT: str = "client"
GRAPH_TYPES: tuple[str, str] = (GRAPH_TYPE_SERVER, GRAPH_TYPE_CLIENT)


def _scan_placeholder_usage_from_graph_code_file(
    *,
    graph_code_file: Path,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """扫描单个节点图源码文件内的 ui_key/entity_key/component_key 占位符集合。"""
    from ugc_file_tools.ui_integration._common import scan_id_ref_placeholders_in_graph_code_file
    from ugc_file_tools.ui_integration.export_center.backfill_inspector import scan_ui_key_placeholders_in_graph_code_files

    ui_usage = scan_ui_key_placeholders_in_graph_code_files(graph_code_files=[Path(graph_code_file)])
    id_ref_usage = scan_id_ref_placeholders_in_graph_code_file(graph_code_file=Path(graph_code_file))
    return (
        frozenset(ui_usage.ui_keys),
        frozenset(id_ref_usage.entity_names),
        frozenset(id_ref_usage.component_names),
    )


@dataclass(frozen=True, slots=True)
class GraphScanFailure:
    graph_file: str
    graph_id: str
    reason: str


def _extract_module_docstring(source_text: str) -> str:
    """提取 Python 模块首个 docstring（无需构建 AST）。"""
    readline = io.StringIO(str(source_text or "")).readline
    for tok in tokenize.generate_tokens(readline):
        if tok.type in {
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.COMMENT,
            tokenize.ENCODING,
        }:
            continue
        if tok.type == tokenize.STRING:
            value = ast.literal_eval(tok.string)
            return value if isinstance(value, str) else ""
        return ""
    return ""


def infer_graph_id_from_graph_code_text(*, text: str) -> str:
    """从节点图源码 docstring 中提取 graph_id。"""
    docstring = _extract_module_docstring(text)
    meta = extract_metadata_from_docstring(docstring) if docstring else None
    graph_id = str(getattr(meta, "graph_id", "") or "").strip() if meta is not None else ""
    return graph_id


def infer_graph_name_from_graph_code_text(*, text: str) -> str:
    """从节点图源码 docstring 中提取 graph_name。"""
    docstring = _extract_module_docstring(text)
    meta = extract_metadata_from_docstring(docstring) if docstring else None
    graph_name = str(getattr(meta, "graph_name", "") or "").strip() if meta is not None else ""
    return graph_name


def iter_graph_code_files(*, resource_root_dir: Path) -> Iterable[Path]:
    """枚举给定资源根目录下的所有节点图源码文件。"""
    root = Path(resource_root_dir).resolve()
    graph_root = (root / GRAPH_DIRNAME).resolve()
    if not graph_root.is_dir():
        return []

    out: list[Path] = []
    for gt in GRAPH_TYPES:
        type_dir = graph_root / gt
        if not type_dir.is_dir():
            continue
        out.extend([p for p in type_dir.rglob(f"*{GRAPH_CODE_EXTENSION}") if p.is_file()])
    out.sort(key=lambda p: normalize_slash(str(p)).casefold())
    return out


def resolve_scoped_resource_roots(*, resource_library_root: Path, package_id: str, scope: str) -> list[Path]:
    """按 scope 计算需要参与扫描的资源根目录列表。"""
    pkg = str(package_id or "").strip()
    normalized_scope = str(scope or "").strip()
    if normalized_scope not in {"project_only", "shared_only", "project_and_shared"}:
        raise ValueError(f"未知 scope：{normalized_scope!r}")

    if normalized_scope == "shared_only":
        return discover_scoped_resource_root_directories(Path(resource_library_root), active_package_id=None)
    if normalized_scope == "project_only":
        roots = discover_scoped_resource_root_directories(Path(resource_library_root), active_package_id=pkg)
        return [r for r in roots if r.name != "共享"]
    return discover_scoped_resource_root_directories(Path(resource_library_root), active_package_id=pkg)


def load_graph_cache_data_if_compatible(
    *,
    workspace_root: Path,
    graph_id: str,
    graph_code_file: Path,
    current_node_defs_fp: str,
) -> Optional[dict]:
    """读取并校验 graph_cache result_data['data']，兼容时返回 GraphModel.payload。"""
    from engine.resources.persistent_graph_cache_manager import PersistentGraphCacheManager

    gid = str(graph_id or "").strip()
    if gid == "":
        return None

    src = read_source_text(Path(graph_code_file))
    payload = PersistentGraphCacheManager(Path(workspace_root)).read_persistent_graph_cache_payload(gid)
    if not isinstance(payload, dict):
        return None
    if str(payload.get("file_hash") or "").strip() != str(src.md5):
        return None
    if str(payload.get("node_defs_fp") or "").strip() != str(current_node_defs_fp or "").strip():
        return None
    result_data = payload.get("result_data")
    if not isinstance(result_data, dict):
        return None
    data = result_data.get(GRAPH_CACHE_DATA_KEY)
    return data if isinstance(data, dict) else None


def ensure_graph_cache_data(
    *,
    workspace_root: Path,
    graph_id: str,
    graph_code_file: Path,
    current_node_defs_fp: str,
) -> Tuple[Optional[dict], Optional[str]]:
    """确保该图可得到可用的 GraphModel.payload（必要时后台解析生成缓存）。"""
    cached = load_graph_cache_data_if_compatible(
        workspace_root=workspace_root,
        graph_id=graph_id,
        graph_code_file=graph_code_file,
        current_node_defs_fp=current_node_defs_fp,
    )
    if isinstance(cached, dict):
        return cached, None

    from engine.resources.resource_cache_service import ResourceCacheService
    from engine.resources.resource_file_ops import ResourceFileOps
    from engine.resources.resource_state import ResourceIndexState
    from engine.resources.graph_resource_service import GraphResourceService
    from engine.resources.persistent_graph_cache_manager import PersistentGraphCacheManager
    from engine.configs.resource_types import ResourceType

    resource_library_dir = (Path(workspace_root) / "assets" / "资源库").resolve()
    index_state = ResourceIndexState()
    index_state.set_file_path(ResourceType.GRAPH, str(graph_id), Path(graph_code_file).resolve())
    cache_service = ResourceCacheService(max_cache_size=int(GRAPH_CACHE_MEMORY_MAX_SIZE))
    file_ops = ResourceFileOps(resource_library_dir)
    persistent = PersistentGraphCacheManager(Path(workspace_root))
    svc = GraphResourceService(
        Path(workspace_root),
        file_ops=file_ops,
        cache_service=cache_service,
        persistent_graph_cache_manager=persistent,
        index_state=index_state,
        graph_code_generator=None,
    )
    loaded = svc.load_graph(str(graph_id))
    if not isinstance(loaded, dict):
        return None, "解析节点图失败（GraphResourceService.load_graph 返回空）。"

    data = loaded.get(GRAPH_CACHE_DATA_KEY)
    if not isinstance(data, dict):
        return None, "解析节点图成功但 graph_cache result_data['data'] 不是 dict。"

    repaired = load_graph_cache_data_if_compatible(
        workspace_root=workspace_root,
        graph_id=graph_id,
        graph_code_file=graph_code_file,
        current_node_defs_fp=current_node_defs_fp,
    )
    return (repaired if isinstance(repaired, dict) else data), None


def build_usage_index_v1_from_graph_payloads(
    *,
    workspace_root: Path,
    items: Iterable[Tuple[str, Path, dict]],
) -> dict:
    """从一组 (graph_id,file,data) 构建 usage index v1 的 JSON payload。"""
    graphs: dict[str, dict] = {}
    node_by_key: dict[str, dict[str, int]] = {}
    node_by_title: dict[str, dict[str, int]] = {}
    composite_by_id: dict[str, dict[str, int]] = {}
    signals_by_name: dict[str, dict[str, int]] = {}
    ui_key_by_key: dict[str, dict[str, int]] = {}
    entity_key_by_name: dict[str, dict[str, int]] = {}
    component_key_by_name: dict[str, dict[str, int]] = {}

    for graph_id, graph_file, graph_payload in items:
        gid = str(graph_id or "").strip()
        if gid == "" or not isinstance(graph_payload, dict):
            continue

        nodes_obj = graph_payload.get("nodes")
        nodes = nodes_obj if isinstance(nodes_obj, list) else []
        rel = normalize_slash(str(Path(graph_file).resolve().relative_to(Path(workspace_root).resolve())))
        graphs[gid] = {"graph_id": gid, "graph_file": rel}

        ui_keys, entity_names, component_names = _scan_placeholder_usage_from_graph_code_file(graph_code_file=Path(graph_file))
        for ui_key in ui_keys:
            k = str(ui_key or "").strip()
            if k == "":
                continue
            bucket = ui_key_by_key.setdefault(k, {})
            bucket[gid] = int(bucket.get(gid, 0)) + 1
        for name in entity_names:
            k = str(name or "").strip()
            if k == "":
                continue
            bucket = entity_key_by_name.setdefault(k, {})
            bucket[gid] = int(bucket.get(gid, 0)) + 1
        for name in component_names:
            k = str(name or "").strip()
            if k == "":
                continue
            bucket = component_key_by_name.setdefault(k, {})
            bucket[gid] = int(bucket.get(gid, 0)) + 1

        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = str(node.get("title") or "").strip()
            node_def_ref = node.get("node_def_ref")
            if isinstance(title, str) and title != "":
                bucket = node_by_title.setdefault(title, {})
                bucket[gid] = int(bucket.get(gid, 0)) + 1

            if not isinstance(node_def_ref, dict):
                continue
            kind = str(node_def_ref.get("kind") or "").strip()
            key = str(node_def_ref.get("key") or "").strip()
            if kind == "" or key == "":
                continue

            if kind == "composite":
                bucket = composite_by_id.setdefault(key, {})
                bucket[gid] = int(bucket.get(gid, 0)) + 1
                continue

            bucket = node_by_key.setdefault(f"{kind}:{key}", {})
            bucket[gid] = int(bucket.get(gid, 0)) + 1

        sig_counts = collect_signal_name_counts_from_graph_model_payload(graph_model_payload=graph_payload)
        for sig_name, cnt in (sig_counts or {}).items():
            name = str(sig_name or "").strip()
            if name == "":
                continue
            bucket = signals_by_name.setdefault(name, {})
            bucket[gid] = int(bucket.get(gid, 0)) + int(cnt)

    return {
        "version": INDEX_VERSION_V1,
        "graphs": graphs,
        "node_by_key": node_by_key,
        "node_by_title": node_by_title,
        "composite_by_id": composite_by_id,
        "signals_by_name": signals_by_name,
        "ui_key_by_key": ui_key_by_key,
        "entity_key_by_name": entity_key_by_name,
        "component_key_by_name": component_key_by_name,
    }


def dump_index_json(*, payload: dict) -> str:
    """将索引 payload 格式化为 JSON 字符串。"""
    return json.dumps(payload, ensure_ascii=False, indent=2)


def compute_current_node_defs_fp(*, workspace_root: Path) -> str:
    """计算当前节点定义指纹（用于 graph_cache 兼容性判断）。"""
    return str(compute_node_defs_fingerprint(Path(workspace_root))).strip()

