from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


UI_SECTION_KEY = "9"
UI_LAYOUT_REGISTRY_KEY = "501"
UI_RECORD_LIST_KEY = "502"
UI_RECORD_PARENT_KEY = "504"
NODE_GRAPHS_SECTION_KEY = "10"

DEFAULT_MAX_ERRORS = 500
DEFAULT_MAX_PATHS_PER_INT = 20

DEFAULT_LAYOUT_GUID = 1073741825
LIBRARY_ROOT_GUID = 1073741838


@dataclass(frozen=True, slots=True)
class UiIntegrityIssue:
    kind: str
    message: str
    context: Dict[str, Any]


def _repo_root() -> Path:
    """返回仓库根目录路径。"""
    return Path(__file__).resolve().parents[1]


def _as_dict(value: Any, *, label: str) -> Dict[str, Any]:
    """将对象断言为 dict 并返回。"""
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be dict, got {type(value).__name__}")
    return value


def _as_list(value: Any, *, label: str) -> List[Any]:
    """将对象断言为 list 并返回。"""
    if not isinstance(value, list):
        raise TypeError(f"{label} must be list, got {type(value).__name__}")
    return value


def _load_gil_container_or_raise(gil_path: Path) -> None:
    """校验 .gil 容器头与 payload 长度一致性。"""
    from ugc_file_tools.save_patchers.gil_codec import read_gil_container

    read_gil_container(Path(gil_path).resolve())


def _load_raw_dump_object(gil_path: Path) -> Dict[str, Any]:
    """以写回口径（prefer_raw_hex_for_utf8=True）加载 payload_root 数值键对象。"""
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import dump_gil_to_raw_json_object

    return dump_gil_to_raw_json_object(Path(gil_path).resolve())


def _extract_ui_record_list(payload_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 payload_root 提取 UI record list(4/9/502) 并归一化为 list[dict]。"""
    node9 = payload_root.get(UI_SECTION_KEY)
    if node9 is None:
        return []
    if not isinstance(node9, dict):
        raise TypeError("payload_root['9'] must be dict or None")
    value = node9.get(UI_RECORD_LIST_KEY)
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    raise TypeError("payload_root['9']['502'] must be list/dict/None")


def _extract_layout_registry_varint_streams(payload_root: Dict[str, Any]) -> List[str]:
    """从 payload_root 提取 layout registry(4/9/501) 的 `<binary_data>` 字符串列表。"""
    node9 = payload_root.get(UI_SECTION_KEY)
    if node9 is None:
        return []
    if not isinstance(node9, dict):
        raise TypeError("payload_root['9'] must be dict or None")
    value = node9.get(UI_LAYOUT_REGISTRY_KEY)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, str)]
    raise TypeError("payload_root['9']['501'] must be str/list/None")


def _primary_guid(rec: Dict[str, Any]) -> Optional[int]:
    """从 UI record 提取 primary guid（找不到返回 None）。"""
    from ugc_file_tools.ui.readable_dump import extract_primary_guid

    gid = extract_primary_guid(rec)
    return int(gid) if isinstance(gid, int) and int(gid) > 0 else None


def _primary_name(rec: Dict[str, Any]) -> Optional[str]:
    """从 UI record 提取 primary name（找不到返回 None）。"""
    from ugc_file_tools.ui.readable_dump import extract_primary_name

    name = extract_primary_name(rec)
    return str(name) if isinstance(name, str) and str(name).strip() != "" else None


def _children_guids(rec: Dict[str, Any]) -> List[int]:
    """从 UI record 提取 children GUID 列表。"""
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import get_children_guids_from_parent_record

    return [int(x) for x in get_children_guids_from_parent_record(rec) if isinstance(x, int) and int(x) > 0]


def _decode_layout_registry_roots(registry_blobs: List[str]) -> List[int]:
    """解析 layout registry 的 root GUID 列表。"""
    from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import decode_varint_stream

    if not registry_blobs:
        return []
    first = str(registry_blobs[0] or "").strip()
    if first == "":
        return []
    if not first.startswith("<binary_data>"):
        raise ValueError("field_9/501[0] is not <binary_data> varint stream")
    data = parse_binary_data_hex_text(first)
    return [int(x) for x in decode_varint_stream(data)]


def _collect_ints_in_object(obj: Any, *, accept: set[int]) -> set[int]:
    """在任意嵌套对象中收集命中 accept 集合的整数值。"""
    found: set[int] = set()
    stack: List[Any] = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, int):
            if int(cur) in accept:
                found.add(int(cur))
            continue
        if isinstance(cur, list):
            stack.extend(cur)
            continue
        if isinstance(cur, dict):
            stack.extend(cur.values())
            continue
    return found


def _format_path(parts: List[str]) -> str:
    """将 path parts 格式化为可读路径字符串。"""
    return ".".join(parts) if parts else "<root>"


def _find_int_paths(obj: Any, *, targets: set[int], max_paths_per_target: int) -> Dict[int, List[str]]:
    """在任意嵌套对象中查找 targets 的出现路径。"""
    out: Dict[int, List[str]] = {int(t): [] for t in targets}
    if not targets:
        return out
    if max_paths_per_target <= 0:
        raise ValueError("max_paths_per_target must be > 0")

    stack: List[Tuple[Any, List[str]]] = [(obj, [])]
    while stack:
        cur, path = stack.pop()
        if isinstance(cur, int):
            v = int(cur)
            if v in out and len(out[v]) < int(max_paths_per_target):
                out[v].append(_format_path(path))
            continue
        if isinstance(cur, list):
            for idx, item in enumerate(cur):
                stack.append((item, path + [f"[{idx}]"]))
            continue
        if isinstance(cur, dict):
            for k, v in cur.items():
                stack.append((v, path + [str(k)]))
            continue
    return out


def _decode_layout_roots_from_payload_root(payload_root: Dict[str, Any]) -> List[int]:
    """从 payload_root 解码 layout registry roots。"""
    blobs = _extract_layout_registry_varint_streams(payload_root)
    return _decode_layout_registry_roots(blobs)


def _build_record_index(ui_records: List[Dict[str, Any]]) -> Tuple[Dict[int, Dict[str, Any]], List[UiIntegrityIssue]]:
    """构建 guid->record 索引并检查重复 GUID。"""
    issues: List[UiIntegrityIssue] = []
    record_by_guid: Dict[int, Dict[str, Any]] = {}
    counts: Dict[int, int] = {}
    for rec in ui_records:
        gid = _primary_guid(rec)
        if gid is None:
            continue
        counts[gid] = int(counts.get(gid, 0)) + 1
        if gid not in record_by_guid:
            record_by_guid[gid] = rec
    dup = sorted([g for g, c in counts.items() if int(c) >= 2])
    if dup:
        sample = [{"guid": int(g), "count": int(counts.get(int(g), 0))} for g in dup[:20]]
        issues.append(
            UiIntegrityIssue(
                kind="duplicate_guid",
                message="UI record list(4/9/502) 出现重复 GUID。",
                context={"samples": sample, "duplicates_total": int(len(dup))},
            )
        )
    return record_by_guid, issues


def _check_parent_links(record_by_guid: Dict[int, Dict[str, Any]], *, max_errors: int) -> List[UiIntegrityIssue]:
    """检查每个 record 的 parent(504) 是否存在。"""
    issues: List[UiIntegrityIssue] = []
    for gid, rec in record_by_guid.items():
        parent = rec.get(UI_RECORD_PARENT_KEY)
        if not isinstance(parent, int):
            continue
        if int(parent) <= 0:
            continue
        if int(parent) not in record_by_guid:
            issues.append(
                UiIntegrityIssue(
                    kind="dangling_parent",
                    message="发现 record.parent(504) 指向不存在的 GUID。",
                    context={"guid": int(gid), "name": _primary_name(rec), "parent_504": int(parent)},
                )
            )
            if len(issues) >= int(max_errors):
                return issues
    return issues


def _check_children_links(record_by_guid: Dict[int, Dict[str, Any]], *, max_errors: int) -> List[UiIntegrityIssue]:
    """检查每个 parent 的 children 是否存在且 child.parent 与之匹配。"""
    issues: List[UiIntegrityIssue] = []
    for parent_guid, parent_rec in record_by_guid.items():
        for child_guid in _children_guids(parent_rec):
            child = record_by_guid.get(int(child_guid))
            if child is None:
                issues.append(
                    UiIntegrityIssue(
                        kind="dangling_child",
                        message="发现 parent.children 引用了不存在的 GUID。",
                        context={
                            "parent_guid": int(parent_guid),
                            "parent_name": _primary_name(parent_rec),
                            "missing_child_guid": int(child_guid),
                        },
                    )
                )
                if len(issues) >= int(max_errors):
                    return issues
                continue
            child_parent = child.get(UI_RECORD_PARENT_KEY)
            if isinstance(child_parent, int) and int(child_parent) > 0 and int(child_parent) != int(parent_guid):
                issues.append(
                    UiIntegrityIssue(
                        kind="child_parent_mismatch",
                        message="发现 parent.children 与 child.parent(504) 不一致。",
                        context={
                            "parent_guid": int(parent_guid),
                            "parent_name": _primary_name(parent_rec),
                            "child_guid": int(child_guid),
                            "child_name": _primary_name(child),
                            "child_parent_504": int(child_parent),
                        },
                    )
                )
                if len(issues) >= int(max_errors):
                    return issues
    return issues


def _check_layout_registry(
    payload_root: Dict[str, Any],
    *,
    record_by_guid: Dict[int, Dict[str, Any]],
    max_errors: int,
) -> List[UiIntegrityIssue]:
    """检查 layout registry 中的 root GUID 是否存在并符合“无 parent”的约定。"""
    issues: List[UiIntegrityIssue] = []
    blobs = _extract_layout_registry_varint_streams(payload_root)
    roots = _decode_layout_registry_roots(blobs)
    if not roots:
        issues.append(
            UiIntegrityIssue(
                kind="layout_registry_empty",
                message="layout registry(4/9/501[0]) 未解析到任何 root GUID。",
                context={"field_9_501_total": int(len(blobs))},
            )
        )
        return issues

    for guid in roots:
        rec = record_by_guid.get(int(guid))
        if rec is None:
            issues.append(
                UiIntegrityIssue(
                    kind="layout_root_missing",
                    message="layout registry 指向的 root GUID 在 record_list 中不存在。",
                    context={"layout_root_guid": int(guid)},
                )
            )
            if len(issues) >= int(max_errors):
                return issues
            continue
        parent = rec.get(UI_RECORD_PARENT_KEY)
        if isinstance(parent, int) and int(parent) > 0:
            issues.append(
                UiIntegrityIssue(
                    kind="layout_root_has_parent",
                    message="layout registry 指向的 root record 仍带 parent(504)。",
                    context={
                        "layout_root_guid": int(guid),
                        "layout_root_name": _primary_name(rec),
                        "parent_504": int(parent),
                    },
                )
            )
            if len(issues) >= int(max_errors):
                return issues

    if int(LIBRARY_ROOT_GUID) not in roots:
        issues.append(
            UiIntegrityIssue(
                kind="library_root_not_in_registry",
                message="layout registry 未包含库根 GUID(1073741838)。",
                context={"library_root_guid": int(LIBRARY_ROOT_GUID)},
            )
        )
    if int(DEFAULT_LAYOUT_GUID) not in roots:
        issues.append(
            UiIntegrityIssue(
                kind="default_layout_not_in_registry",
                message="layout registry 未包含默认布局 GUID(1073741825)。",
                context={"default_layout_guid": int(DEFAULT_LAYOUT_GUID)},
            )
        )
    return issues


def diagnose_gil_ui_integrity(*, input_gil: Path, max_errors: int) -> Dict[str, Any]:
    """对 .gil 的 UI 段做一致性体检并输出结构化报告。"""
    input_path = Path(input_gil).resolve()
    _load_gil_container_or_raise(input_path)

    raw_dump = _load_raw_dump_object(input_path)
    payload_root = _as_dict(raw_dump.get("4"), label="dump['4']")

    ui_records = _extract_ui_record_list(payload_root)
    record_by_guid, issues = _build_record_index(ui_records)

    issues.extend(_check_layout_registry(payload_root, record_by_guid=record_by_guid, max_errors=max_errors))
    if len(issues) < int(max_errors):
        issues.extend(_check_parent_links(record_by_guid, max_errors=max_errors - len(issues)))
    if len(issues) < int(max_errors):
        issues.extend(_check_children_links(record_by_guid, max_errors=max_errors - len(issues)))

    summaries = {
        "ui_section_present": payload_root.get(UI_SECTION_KEY) is not None,
        "ui_records_total": int(len(ui_records)),
        "ui_records_indexed_total": int(len(record_by_guid)),
        "issues_total": int(len(issues)),
        "issues_truncated": bool(len(issues) >= int(max_errors)),
    }
    return {
        "input_gil": str(input_path),
        "summary": summaries,
        "issues": [
            {"kind": it.kind, "message": it.message, "context": dict(it.context)}
            for it in issues[: int(max_errors)]
        ],
    }


def diagnose_gil_ui_cross_refs(*, baseline_gil: Path, target_gil: Path) -> Dict[str, Any]:
    """诊断节点图段对 UI layout roots 的引用是否在 target 的 UI records 中存在。"""
    base_raw = _load_raw_dump_object(Path(baseline_gil).resolve())
    base_root = _as_dict(base_raw.get("4"), label="baseline dump['4']")
    base_layout_roots = _decode_layout_roots_from_payload_root(base_root)

    target_raw = _load_raw_dump_object(Path(target_gil).resolve())
    target_root = _as_dict(target_raw.get("4"), label="target dump['4']")
    target_layout_roots = _decode_layout_roots_from_payload_root(target_root)

    target_ui_records = _extract_ui_record_list(target_root)
    target_record_by_guid, _issues0 = _build_record_index(target_ui_records)

    candidate_layout_roots = {int(x) for x in list(base_layout_roots) + list(target_layout_roots) if isinstance(x, int) and int(x) > 0}
    section10 = target_root.get(NODE_GRAPHS_SECTION_KEY)
    referenced = _collect_ints_in_object(section10, accept=set(candidate_layout_roots)) if candidate_layout_roots else set()

    missing_in_target_ui = sorted([int(x) for x in referenced if int(x) not in target_record_by_guid])
    missing_paths = (
        _find_int_paths(section10, targets=set(missing_in_target_ui), max_paths_per_target=int(DEFAULT_MAX_PATHS_PER_INT))
        if missing_in_target_ui
        else {}
    )
    return {
        "baseline_gil": str(Path(baseline_gil).resolve()),
        "target_gil": str(Path(target_gil).resolve()),
        "baseline_layout_roots_total": int(len(base_layout_roots)),
        "target_layout_roots_total": int(len(target_layout_roots)),
        "candidate_layout_roots_total": int(len(candidate_layout_roots)),
        "referenced_layout_roots_total": int(len(referenced)),
        "referenced_layout_roots": sorted(list(referenced)),
        "missing_referenced_roots_in_target_ui_total": int(len(missing_in_target_ui)),
        "missing_referenced_roots_in_target_ui": missing_in_target_ui,
        "missing_referenced_roots_in_target_section10_paths": {str(k): list(v) for k, v in missing_paths.items()},
    }


def _default_report_path(input_gil: Path) -> Path:
    """生成默认报告路径（落在 tmp/ 下）。"""
    stem = Path(input_gil).resolve().stem
    out_dir = (_repo_root() / "tmp" / "gil_ui_integrity").resolve()
    return out_dir / f"{stem}.report.json"


def _write_report(path: Path, report: Dict[str, Any]) -> None:
    """将报告以 UTF-8 JSON 写入磁盘。"""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    """解析参数并执行 UI 体检脚本。"""
    parser = argparse.ArgumentParser(description="Diagnose .gil UI section integrity (4/9).")
    parser.add_argument("--input", required=True, help="Input .gil path")
    parser.add_argument("--baseline", default="", help="Optional baseline .gil path for cross-ref check (node graphs -> UI layout roots)")
    parser.add_argument("--report", default="", help="Output report.json path (default: repo/tmp/gil_ui_integrity/<stem>.report.json)")
    parser.add_argument("--max-errors", type=int, default=int(DEFAULT_MAX_ERRORS), help="Max issues to record in report (default: 500)")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root / "private_extensions"))

    input_gil = Path(str(args.input))
    max_errors = int(args.max_errors)
    if max_errors <= 0:
        raise ValueError("--max-errors must be > 0")
    report = diagnose_gil_ui_integrity(input_gil=Path(input_gil), max_errors=max_errors)

    baseline_text = str(args.baseline or "").strip()
    if baseline_text != "":
        report["cross_refs"] = diagnose_gil_ui_cross_refs(baseline_gil=Path(baseline_text), target_gil=Path(input_gil))

    report_path = Path(str(args.report)).resolve() if str(args.report or "").strip() != "" else _default_report_path(input_gil)
    _write_report(report_path, report)

    summary = _as_dict(report.get("summary"), label="report['summary']")
    print(str(input_gil.resolve()))
    print(f"ui_section_present={bool(summary.get('ui_section_present'))}")
    print(f"ui_records_total={int(summary.get('ui_records_total') or 0)} indexed={int(summary.get('ui_records_indexed_total') or 0)}")
    print(f"issues_total={int(summary.get('issues_total') or 0)} truncated={bool(summary.get('issues_truncated'))}")
    print(f"report={str(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

