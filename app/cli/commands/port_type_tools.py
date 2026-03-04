from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class _NodeDefResolutionIssue:
    node_id: str
    title: str
    category: str
    kind: str
    key: str
    mapped_builtin_key: str
    issue: str  # "title_fallback_hit" | "unresolved_even_with_title_fallback"


@dataclass(frozen=True)
class _GraphScanResult:
    graph_code_file: str
    graph_id: str
    graph_name: str
    graph_scope: str
    parse_mode: str  # "strict" | "non_strict"
    nodes_total: int
    title_fallback_hits: int
    unresolved_even_with_title_fallback: int
    issues: list[_NodeDefResolutionIssue]
    error: str


@dataclass(frozen=True)
class _EventNodeDefMigrationIssue:
    node_id: str
    title: str
    category: str
    event_key: str
    mapped_builtin_key: str
    status: str  # "mappable" | "missing_category_or_title" | "mapped_builtin_key_not_found"


@dataclass(frozen=True)
class _EventMigrationScanResult:
    graph_code_file: str
    graph_id: str
    graph_name: str
    graph_scope: str
    parse_mode: str  # "strict" | "non_strict"
    nodes_total: int
    event_nodes_total: int
    mappable: int
    missing_category_or_title: int
    mapped_builtin_key_not_found: int
    issues: list[_EventNodeDefMigrationIssue]
    error: str


def register_port_type_tools_commands(subparsers: argparse._SubParsersAction) -> None:
    scan_parser = subparsers.add_parser(
        "scan-title-fallback",
        help="离线诊断：扫描 NodeDef 定位是否依赖 title fallback（仅供迁移/兼容诊断）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    scan_parser.add_argument(
        "paths",
        nargs="+",
        help="节点图 GraphCode 文件或目录（相对 workspace_root 或绝对路径；目录会递归扫描 .py）",
    )
    scan_parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        help="严格解析（GraphCodeParser(strict=True)）；默认非严格（用于批量诊断/迁移）。",
    )
    scan_parser.add_argument(
        "--out",
        default="tmp/artifacts/port_type_title_fallback_scan.json",
        help="输出 JSON 报告路径（相对 workspace_root 或绝对路径）。默认 tmp/artifacts/port_type_title_fallback_scan.json",
    )
    scan_parser.set_defaults(_runner=run_scan_title_fallback)

    event_parser = subparsers.add_parser(
        "scan-event-migration",
        help="离线诊断：扫描 event 节点是否可迁移为 builtin/composite ref（仅输出报告，不改写源码）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    event_parser.add_argument(
        "paths",
        nargs="+",
        help="节点图 GraphCode 文件或目录（相对 workspace_root 或绝对路径；目录会递归扫描 .py）",
    )
    event_parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        help="严格解析（GraphCodeParser(strict=True)）；默认非严格（用于批量诊断/迁移）。",
    )
    event_parser.add_argument(
        "--out",
        default="tmp/artifacts/port_type_event_migration_scan.json",
        help="输出 JSON 报告路径（相对 workspace_root 或绝对路径）。默认 tmp/artifacts/port_type_event_migration_scan.json",
    )
    event_parser.set_defaults(_runner=run_scan_event_migration)


def run_scan_title_fallback(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
    from engine import get_node_registry, GraphCodeParser
    # 关键：`ugc_file_tools.*` 位于 `private_extensions/` 下；CLI 环境下需先以
    # `private_extensions.ugc_file_tools` 导入触发 alias（sys.modules['ugc_file_tools']）。
    import private_extensions.ugc_file_tools  # noqa: F401

    from ugc_file_tools.graph.port_types import load_node_library_maps_from_registry
    from ugc_file_tools.graph import port_types as port_types_mod

    strict = bool(getattr(parsed_args, "strict", False))
    parse_mode = "strict" if strict else "non_strict"

    input_paths = _expand_graph_code_paths(workspace_root=workspace_root, raw_paths=getattr(parsed_args, "paths", []))
    out_path = _resolve_out_path(workspace_root=workspace_root, raw_out=str(getattr(parsed_args, "out", "") or ""))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[_GraphScanResult] = []
    total_title_hits = 0
    total_unresolved = 0
    total_errors = 0

    registry = get_node_registry(workspace_root, include_composite=True)
    node_library = registry.get_library()
    parser = GraphCodeParser(workspace_root, node_library=node_library, strict=bool(strict))

    maps_by_scope: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}

    for code_path in input_paths:
        try:
            graph_meta = load_graph_metadata_from_file(code_path)
            graph_id = str(getattr(graph_meta, "graph_id", "") or "").strip()
            if not graph_id:
                raise ValueError("节点图源码未声明 graph_id（docstring metadata）")

            graph_model, metadata = parser.parse_file(code_path)
            graph_payload = graph_model.serialize()
            graph_scope = str(
                metadata.get("graph_type")
                or metadata.get("scope")
                or (graph_payload.get("metadata") or {}).get("graph_type")
                or "server"
            ).strip() or "server"
            graph_name = str(metadata.get("graph_name") or metadata.get("name") or "").strip()

            if graph_scope not in maps_by_scope:
                maps_by_scope[graph_scope] = load_node_library_maps_from_registry(
                    workspace_root=workspace_root,
                    scope=graph_scope,
                    include_composite=True,
                )
            node_defs_by_name, node_defs_by_key, composite_node_def_by_id = maps_by_scope[graph_scope]

            issues = _scan_graph_model_node_def_resolution_issues(
                graph_model=graph_model,
                node_defs_by_name=node_defs_by_name,
                node_defs_by_key=node_defs_by_key,
                composite_node_def_by_id=composite_node_def_by_id,
                resolve_node_def_for_model=getattr(port_types_mod, "_resolve_node_def_for_model"),
            )

            title_hits = sum(1 for i in issues if i.issue == "title_fallback_hit")
            unresolved = sum(1 for i in issues if i.issue == "unresolved_even_with_title_fallback")

            total_title_hits += int(title_hits)
            total_unresolved += int(unresolved)

            results.append(
                _GraphScanResult(
                    graph_code_file=str(code_path),
                    graph_id=str(graph_id),
                    graph_name=str(graph_name),
                    graph_scope=str(graph_scope),
                    parse_mode=str(parse_mode),
                    nodes_total=len(getattr(graph_model, "nodes", {}) or {}),
                    title_fallback_hits=int(title_hits),
                    unresolved_even_with_title_fallback=int(unresolved),
                    issues=list(issues),
                    error="",
                )
            )
        except Exception as e:
            total_errors += 1
            results.append(
                _GraphScanResult(
                    graph_code_file=str(code_path),
                    graph_id="",
                    graph_name="",
                    graph_scope="",
                    parse_mode=str(parse_mode),
                    nodes_total=0,
                    title_fallback_hits=0,
                    unresolved_even_with_title_fallback=0,
                    issues=[],
                    error=f"{type(e).__name__}: {e}",
                )
            )

    out_payload = {
        "workspace_root": str(Path(workspace_root).resolve()),
        "parse_mode": str(parse_mode),
        "graphs_total": len(results),
        "graphs_with_title_fallback_hits": sum(1 for r in results if r.title_fallback_hits > 0),
        "graphs_with_unresolved_nodes": sum(1 for r in results if r.unresolved_even_with_title_fallback > 0),
        "graphs_with_errors": sum(1 for r in results if r.error),
        "total_title_fallback_hits": int(total_title_hits),
        "total_unresolved_even_with_title_fallback": int(total_unresolved),
        "results": [_graph_scan_result_to_json(r) for r in results],
    }
    out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] 写入报告：{out_path}")
    print(
        "[SUMMARY] "
        f"graphs={out_payload['graphs_total']}, "
        f"title_fallback_hits={out_payload['total_title_fallback_hits']}, "
        f"unresolved={out_payload['total_unresolved_even_with_title_fallback']}, "
        f"errors={out_payload['graphs_with_errors']}"
    )

    if int(total_title_hits) > 0 or int(total_unresolved) > 0 or int(total_errors) > 0:
        return 1
    return 0


def run_scan_event_migration(parsed_args: argparse.Namespace, workspace_root: Path) -> int:
    from engine import get_node_registry, GraphCodeParser

    # 触发 `private_extensions/ugc_file_tools` 的 import-root 注入与顶层包 alias（ugc_file_tools）。
    import private_extensions.ugc_file_tools  # noqa: F401

    from ugc_file_tools.graph.port_types import load_node_library_maps_from_registry

    strict = bool(getattr(parsed_args, "strict", False))
    parse_mode = "strict" if strict else "non_strict"

    input_paths = _expand_graph_code_paths(workspace_root=workspace_root, raw_paths=getattr(parsed_args, "paths", []))
    out_path = _resolve_out_path(workspace_root=workspace_root, raw_out=str(getattr(parsed_args, "out", "") or ""))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    registry = get_node_registry(workspace_root, include_composite=True)
    node_library = registry.get_library()
    parser = GraphCodeParser(workspace_root, node_library=node_library, strict=bool(strict))

    maps_by_scope: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}

    results = [
        _scan_event_migration_for_one_graph_code_file(
            code_path=code_path,
            workspace_root=workspace_root,
            parse_mode=parse_mode,
            parser=parser,
            maps_by_scope=maps_by_scope,
            load_node_library_maps_from_registry=load_node_library_maps_from_registry,
        )
        for code_path in input_paths
    ]
    out_payload = _build_event_migration_out_payload(workspace_root=workspace_root, parse_mode=parse_mode, results=results)
    out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] 写入报告：{out_path}")
    print(
        "[SUMMARY] "
        f"graphs={out_payload['graphs_total']}, "
        f"mappable={out_payload['total_mappable']}, "
        f"missing_fields={out_payload['total_missing_category_or_title']}, "
        f"mapped_key_not_found={out_payload['total_mapped_builtin_key_not_found']}, "
        f"errors={out_payload['graphs_with_errors']}"
    )

    if (
        int(out_payload["total_missing_category_or_title"]) > 0
        or int(out_payload["total_mapped_builtin_key_not_found"]) > 0
        or int(out_payload["graphs_with_errors"]) > 0
    ):
        return 1
    return 0


def _scan_event_migration_for_one_graph_code_file(
    *,
    code_path: Path,
    workspace_root: Path,
    parse_mode: str,
    parser: Any,
    maps_by_scope: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    load_node_library_maps_from_registry: Any,
) -> _EventMigrationScanResult:
    try:
        graph_id = _load_graph_id_or_raise(code_path)
        graph_model, metadata = parser.parse_file(code_path)
        graph_scope, graph_name = _resolve_graph_scope_and_name(graph_model=graph_model, metadata=metadata)
        node_defs_by_key = _get_node_defs_by_key_for_scope(
            workspace_root=workspace_root,
            graph_scope=graph_scope,
            maps_by_scope=maps_by_scope,
            load_node_library_maps_from_registry=load_node_library_maps_from_registry,
        )

        issues = _scan_graph_model_event_node_def_migration_issues(graph_model=graph_model, node_defs_by_key=node_defs_by_key)
        mappable, missing_fields, key_not_found = _count_event_migration_issue_statuses(issues)

        return _EventMigrationScanResult(
            graph_code_file=str(code_path),
            graph_id=str(graph_id),
            graph_name=str(graph_name),
            graph_scope=str(graph_scope),
            parse_mode=str(parse_mode),
            nodes_total=len(getattr(graph_model, "nodes", {}) or {}),
            event_nodes_total=len(issues),
            mappable=int(mappable),
            missing_category_or_title=int(missing_fields),
            mapped_builtin_key_not_found=int(key_not_found),
            issues=list(issues),
            error="",
        )
    except Exception as e:
        return _EventMigrationScanResult(
            graph_code_file=str(code_path),
            graph_id="",
            graph_name="",
            graph_scope="",
            parse_mode=str(parse_mode),
            nodes_total=0,
            event_nodes_total=0,
            mappable=0,
            missing_category_or_title=0,
            mapped_builtin_key_not_found=0,
            issues=[],
            error=f"{type(e).__name__}: {e}",
        )


def _load_graph_id_or_raise(code_path: Path) -> str:
    from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file

    graph_meta = load_graph_metadata_from_file(code_path)
    graph_id = str(getattr(graph_meta, "graph_id", "") or "").strip()
    if not graph_id:
        raise ValueError("节点图源码未声明 graph_id（docstring metadata）")
    return graph_id


def _resolve_graph_scope_and_name(*, graph_model: Any, metadata: Any) -> tuple[str, str]:
    graph_payload = graph_model.serialize()
    graph_scope = str(
        metadata.get("graph_type") or metadata.get("scope") or (graph_payload.get("metadata") or {}).get("graph_type") or "server"
    ).strip() or "server"
    graph_name = str(metadata.get("graph_name") or metadata.get("name") or "").strip()
    return graph_scope, graph_name


def _get_node_defs_by_key_for_scope(
    *,
    workspace_root: Path,
    graph_scope: str,
    maps_by_scope: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    load_node_library_maps_from_registry: Any,
) -> dict[str, Any]:
    scope = str(graph_scope or "").strip() or "server"
    if scope not in maps_by_scope:
        maps_by_scope[scope] = load_node_library_maps_from_registry(
            workspace_root=workspace_root,
            scope=scope,
            include_composite=True,
        )
    _node_defs_by_name, node_defs_by_key, _composite_node_def_by_id = maps_by_scope[scope]
    return dict(node_defs_by_key or {})


def _count_event_migration_issue_statuses(issues: list[_EventNodeDefMigrationIssue]) -> tuple[int, int, int]:
    mappable = sum(1 for i in issues if i.status == "mappable")
    missing_fields = sum(1 for i in issues if i.status == "missing_category_or_title")
    key_not_found = sum(1 for i in issues if i.status == "mapped_builtin_key_not_found")
    return int(mappable), int(missing_fields), int(key_not_found)


def _build_event_migration_out_payload(
    *,
    workspace_root: Path,
    parse_mode: str,
    results: list[_EventMigrationScanResult],
) -> dict[str, Any]:
    return {
        "workspace_root": str(Path(workspace_root).resolve()),
        "parse_mode": str(parse_mode),
        "graphs_total": len(results),
        "graphs_with_event_nodes": sum(1 for r in results if r.event_nodes_total > 0),
        "graphs_with_errors": sum(1 for r in results if r.error),
        "total_mappable": int(sum(r.mappable for r in results)),
        "total_missing_category_or_title": int(sum(r.missing_category_or_title for r in results)),
        "total_mapped_builtin_key_not_found": int(sum(r.mapped_builtin_key_not_found for r in results)),
        "results": [_event_migration_scan_result_to_json(r) for r in results],
    }


def _expand_graph_code_paths(*, workspace_root: Path, raw_paths: object) -> list[Path]:
    raw_list = raw_paths if isinstance(raw_paths, list) else list(raw_paths or [])
    out: list[Path] = []
    seen: set[Path] = set()

    for p in raw_list:
        text = str(p or "").strip()
        if not text:
            continue
        path = Path(text)
        if not path.is_absolute():
            path = (workspace_root / path).resolve()
        if not path.exists():
            raise FileNotFoundError(str(path))
        if path.is_file():
            if path.suffix.lower() == ".py":
                if path not in seen:
                    seen.add(path)
                    out.append(path)
            continue
        if path.is_dir():
            for f in sorted(path.rglob("*.py")):
                fp = f.resolve()
                if fp not in seen:
                    seen.add(fp)
                    out.append(fp)
            continue

    return out


def _resolve_out_path(*, workspace_root: Path, raw_out: str) -> Path:
    out_text = str(raw_out or "").strip()
    out_path = Path(out_text) if out_text else Path("tmp/artifacts/port_type_title_fallback_scan.json")
    if not out_path.is_absolute():
        out_path = (workspace_root / out_path).resolve()
    return out_path


def _scan_graph_model_node_def_resolution_issues(
    *,
    graph_model: Any,
    node_defs_by_name: dict[str, Any],
    node_defs_by_key: dict[str, Any],
    composite_node_def_by_id: dict[str, Any],
    resolve_node_def_for_model: Any,
) -> list[_NodeDefResolutionIssue]:
    node_model_by_id = getattr(graph_model, "nodes", {}) or {}
    if not isinstance(node_model_by_id, dict) or not node_model_by_id:
        return []

    issues: list[_NodeDefResolutionIssue] = []
    for node_id, node_model in list(node_model_by_id.items()):
        nid = str(node_id or "")
        if node_model is None:
            continue

        resolved_without = resolve_node_def_for_model(
            node_model,
            node_defs_by_name=node_defs_by_name,
            node_defs_by_key=node_defs_by_key,
            composite_node_def_by_id=composite_node_def_by_id,
            allow_title_fallback=False,
        )
        if resolved_without is not None:
            continue

        resolved_with = resolve_node_def_for_model(
            node_model,
            node_defs_by_name=node_defs_by_name,
            node_defs_by_key=node_defs_by_key,
            composite_node_def_by_id=composite_node_def_by_id,
            allow_title_fallback=True,
        )

        title = str(getattr(node_model, "title", "") or "").strip()
        category = str(getattr(node_model, "category", "") or "").strip()
        node_def_ref = getattr(node_model, "node_def_ref", None)
        kind = str(getattr(node_def_ref, "kind", "") or "").strip() if node_def_ref is not None else ""
        key = str(getattr(node_def_ref, "key", "") or "").strip() if node_def_ref is not None else ""
        mapped_builtin_key = f"{category}/{title}" if (kind == "event" and category and title) else ""

        issues.append(
            _NodeDefResolutionIssue(
                node_id=nid,
                title=title,
                category=category,
                kind=kind,
                key=key,
                mapped_builtin_key=mapped_builtin_key,
                issue="title_fallback_hit" if resolved_with is not None else "unresolved_even_with_title_fallback",
            )
        )
    return issues


def _graph_scan_result_to_json(r: _GraphScanResult) -> dict[str, Any]:
    return {
        "graph_code_file": r.graph_code_file,
        "graph_id": r.graph_id,
        "graph_name": r.graph_name,
        "graph_scope": r.graph_scope,
        "parse_mode": r.parse_mode,
        "nodes_total": r.nodes_total,
        "title_fallback_hits": r.title_fallback_hits,
        "unresolved_even_with_title_fallback": r.unresolved_even_with_title_fallback,
        "issues": [
            {
                "node_id": i.node_id,
                "title": i.title,
                "category": i.category,
                "node_def_ref": {
                    "kind": i.kind,
                    "key": i.key,
                },
                "event_mapped_builtin_key": i.mapped_builtin_key,
                "issue": i.issue,
            }
            for i in (r.issues or [])
        ],
        "error": r.error,
    }


def _scan_graph_model_event_node_def_migration_issues(
    *,
    graph_model: Any,
    node_defs_by_key: dict[str, Any],
) -> list[_EventNodeDefMigrationIssue]:
    node_model_by_id = getattr(graph_model, "nodes", {}) or {}
    if not isinstance(node_model_by_id, dict) or not node_model_by_id:
        return []

    out: list[_EventNodeDefMigrationIssue] = []
    for node_id, node_model in list(node_model_by_id.items()):
        nid = str(node_id or "")
        if node_model is None:
            continue
        node_def_ref = getattr(node_model, "node_def_ref", None)
        kind = str(getattr(node_def_ref, "kind", "") or "").strip() if node_def_ref is not None else ""
        if kind != "event":
            continue
        event_key = str(getattr(node_def_ref, "key", "") or "").strip() if node_def_ref is not None else ""
        title = str(getattr(node_model, "title", "") or "").strip()
        category = str(getattr(node_model, "category", "") or "").strip()
        mapped_builtin_key = f"{category}/{title}" if (category and title) else ""

        if not (category and title):
            status = "missing_category_or_title"
        elif mapped_builtin_key not in (node_defs_by_key or {}):
            status = "mapped_builtin_key_not_found"
        else:
            status = "mappable"

        out.append(
            _EventNodeDefMigrationIssue(
                node_id=nid,
                title=title,
                category=category,
                event_key=event_key,
                mapped_builtin_key=mapped_builtin_key,
                status=status,
            )
        )
    return out


def _event_migration_scan_result_to_json(r: _EventMigrationScanResult) -> dict[str, Any]:
    return {
        "graph_code_file": r.graph_code_file,
        "graph_id": r.graph_id,
        "graph_name": r.graph_name,
        "graph_scope": r.graph_scope,
        "parse_mode": r.parse_mode,
        "nodes_total": r.nodes_total,
        "event_nodes_total": r.event_nodes_total,
        "mappable": r.mappable,
        "missing_category_or_title": r.missing_category_or_title,
        "mapped_builtin_key_not_found": r.mapped_builtin_key_not_found,
        "issues": [
            {
                "node_id": i.node_id,
                "title": i.title,
                "category": i.category,
                "node_def_ref": {"kind": "event", "key": i.event_key},
                "event_mapped_builtin_key": i.mapped_builtin_key,
                "status": i.status,
            }
            for i in (r.issues or [])
        ],
        "error": r.error,
    }

