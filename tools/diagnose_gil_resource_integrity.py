from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MIN_TEMPLATE_ENTRY_ID_INT = 1_000_000_000
DEFAULT_MAX_ISSUES = 500

SECTION_TEMPLATES_KEY = "4"
SECTION_INSTANCES_KEY = "5"
SECTION_ROOT8_KEY = "8"
SECTION_TABS_KEY = "6"
SECTION_DECORATIONS_KEY = "27"

REPEATED_ENTRIES_KEY = "1"

META_LIST_KEY = "5"
META_KIND_KEY = "1"
META_PAYLOAD_KEY_40 = "50"


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    kind: str
    message: str
    context: Dict[str, Any]


def _repo_root() -> Path:
    """返回仓库根目录路径。"""
    return Path(__file__).resolve().parents[1]


def _load_raw_payload_root(gil_path: Path) -> Dict[str, Any]:
    """以工具链写回口径加载 payload_root 数值键 dict。"""
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import dump_gil_to_raw_json_object

    raw = dump_gil_to_raw_json_object(Path(gil_path).resolve())
    payload_root = raw.get("4")
    if not isinstance(payload_root, dict):
        raise TypeError("dump['4'] must be dict")
    return payload_root


def _read_gil_container_or_raise(gil_path: Path) -> None:
    """校验 .gil 容器头与 payload 长度一致性。"""
    from ugc_file_tools.save_patchers.gil_codec import read_gil_container

    read_gil_container(Path(gil_path).resolve())


def _as_list_allow_scalar(value: Any) -> List[Any]:
    """将 list/dict/None 归一化为 list。"""
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


def _extract_template_entry_id_int(template_entry: Dict[str, Any]) -> Optional[int]:
    """从模板 entry 提取 template_entry_id_int（prefab_id）。"""
    v1 = template_entry.get("1")
    if isinstance(v1, int):
        return int(v1)
    if isinstance(v1, list) and v1 and isinstance(v1[0], int):
        return int(v1[0])
    return None


def _collect_template_entry_ids(payload_root: Dict[str, Any]) -> set[int]:
    """收集 root4/4/1 中的模板条目 ID 集合。"""
    sec4 = payload_root.get(SECTION_TEMPLATES_KEY)
    if not isinstance(sec4, dict):
        return set()
    entries = _as_list_allow_scalar(sec4.get(REPEATED_ENTRIES_KEY))
    out: set[int] = set()
    for it in entries:
        if not isinstance(it, dict):
            continue
        tid = _extract_template_entry_id_int(it)
        if isinstance(tid, int) and int(tid) >= int(MIN_TEMPLATE_ENTRY_ID_INT):
            out.add(int(tid))
    return out


def _extract_instance_id_int(instance_entry: Dict[str, Any]) -> Optional[int]:
    """从实例 entry 提取 instance_id_int。"""
    v1 = instance_entry.get("1")
    if isinstance(v1, int):
        return int(v1)
    if isinstance(v1, list) and v1 and isinstance(v1[0], int):
        return int(v1[0])
    return None


def _extract_instance_template_id_int(instance_entry: Dict[str, Any]) -> Optional[int]:
    """从实例 entry 提取 template_id_int（record['2']['1']）。"""
    v2 = instance_entry.get("2")
    if isinstance(v2, dict) and isinstance(v2.get("1"), int):
        return int(v2.get("1"))
    if isinstance(v2, list) and v2 and isinstance(v2[0], dict) and isinstance(v2[0].get("1"), int):
        return int(v2[0].get("1"))
    return None


def _collect_instance_ids(payload_root: Dict[str, Any]) -> set[int]:
    """收集 root4/5/1 与 root8/1 的 instance_id_int 集合。"""
    out: set[int] = set()
    for sec_key in (SECTION_INSTANCES_KEY, SECTION_ROOT8_KEY):
        sec = payload_root.get(sec_key)
        if not isinstance(sec, dict):
            continue
        entries = _as_list_allow_scalar(sec.get(REPEATED_ENTRIES_KEY))
        for it in entries:
            if not isinstance(it, dict):
                continue
            iid = _extract_instance_id_int(it)
            if isinstance(iid, int) and int(iid) > 0:
                out.add(int(iid))
    return out


def _iter_root27_defs_and_atts(payload_root: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """提取 root27 definitions(list1) 与 attachments(list2)。"""
    sec27 = payload_root.get(SECTION_DECORATIONS_KEY)
    if not isinstance(sec27, dict):
        return [], []
    defs = _as_list_allow_scalar(sec27.get("1"))
    atts = _as_list_allow_scalar(sec27.get("2"))
    return [x for x in defs if isinstance(x, dict)], [x for x in atts if isinstance(x, dict)]


def _extract_meta40_parent_id_int(meta_list: List[Any]) -> Optional[int]:
    """从 meta_list 中抽取 meta40.field50.502(parent_id_int)。"""
    for item in list(meta_list):
        if not isinstance(item, dict):
            continue
        if item.get(META_KIND_KEY) != 40:
            continue
        v50 = item.get(META_PAYLOAD_KEY_40)
        if isinstance(v50, dict) and isinstance(v50.get("502"), int):
            return int(v50.get("502"))
    return None


def _extract_root27_def_id_int(def_entry: Dict[str, Any]) -> Optional[int]:
    """从 root27.1(definition) entry 提取 def_id_int。"""
    v1 = def_entry.get("1")
    if isinstance(v1, int):
        return int(v1)
    if isinstance(v1, list) and v1 and isinstance(v1[0], int):
        return int(v1[0])
    return None


def _extract_root27_attachment_def_id_int(att_entry: Dict[str, Any]) -> Optional[int]:
    """从 root27.2(attachment) entry 提取 field12.1(def_id_int) 引用。"""
    v12 = att_entry.get("12")
    if isinstance(v12, dict) and isinstance(v12.get("1"), int):
        return int(v12.get("1"))
    if isinstance(v12, list) and v12 and isinstance(v12[0], dict) and isinstance(v12[0].get("1"), int):
        return int(v12[0].get("1"))
    return None


def _check_root6_template_tabs(payload_root: Dict[str, Any]) -> List[IntegrityIssue]:
    """检查 root4/6 是否存在可用的“未分类页签(kind=100/400)”索引节点。"""
    issues: List[IntegrityIssue] = []
    sec6 = payload_root.get(SECTION_TABS_KEY)
    if sec6 is None:
        issues.append(
            IntegrityIssue(
                kind="missing_root4_6",
                message="缺失 root4/6（模板页签/索引段）。",
                context={},
            )
        )
        return issues
    if not isinstance(sec6, dict):
        issues.append(
            IntegrityIssue(
                kind="bad_root4_6_type",
                message="root4/6 类型异常（期望 dict）。",
                context={"type": type(sec6).__name__},
            )
        )
        return issues

    nodes = _as_list_allow_scalar(sec6.get("1"))
    best: Optional[Dict[str, Any]] = None
    has_any_unclassified = False
    has_any_index_kinds = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        sub3 = node.get("3")
        if not isinstance(sub3, dict):
            continue
        if str(sub3.get("1") or "").strip() != "未分类页签":
            continue
        has_any_unclassified = True
        list5 = _as_list_allow_scalar(sub3.get("5"))
        items = [it for it in list5 if isinstance(it, dict) and isinstance(it.get("1"), int) and isinstance(it.get("2"), int)]
        if not items:
            continue
        has_400 = any(int(it.get("1")) == 400 for it in items if isinstance(it, dict))
        has_100 = any(int(it.get("1")) == 100 for it in items if isinstance(it, dict))
        if has_400 or has_100:
            has_any_index_kinds = True
            best = node
            break

    if not has_any_unclassified:
        issues.append(
            IntegrityIssue(
                kind="root4_6_missing_unclassified_tab",
                message="root4/6 未找到 sub3.1 == '未分类页签' 的节点。",
                context={"nodes_total": int(len(nodes))},
            )
        )
    elif not has_any_index_kinds:
        issues.append(
            IntegrityIssue(
                kind="root4_6_unclassified_missing_index_kinds",
                message="root4/6 的 '未分类页签' 节点缺少 kind=100/400 的索引表条目。",
                context={},
            )
        )
    else:
        issues.append(
            IntegrityIssue(
                kind="root4_6_ok",
                message="root4/6 找到可用的 '未分类页签' 索引节点。",
                context={"sample_node_has_sub3": isinstance((best or {}).get("3"), dict)},
            )
        )
    return issues


def diagnose_gil_resource_integrity(*, input_gil: Path, max_issues: int) -> Dict[str, Any]:
    """对 .gil 的模板/实例/装饰物/页签索引做一致性体检并输出 report。"""
    p = Path(input_gil).resolve()
    _read_gil_container_or_raise(p)
    payload_root = _load_raw_payload_root(p)

    issues: List[IntegrityIssue] = []

    template_entry_ids = _collect_template_entry_ids(payload_root)
    instance_ids = _collect_instance_ids(payload_root)

    sec5 = payload_root.get(SECTION_INSTANCES_KEY)
    instance_entries = []
    if isinstance(sec5, dict):
        instance_entries = [x for x in _as_list_allow_scalar(sec5.get(REPEATED_ENTRIES_KEY)) if isinstance(x, dict)]

    missing_template_refs: List[Dict[str, Any]] = []
    for rec in instance_entries:
        tid = _extract_instance_template_id_int(rec)
        if not isinstance(tid, int):
            continue
        if int(tid) < int(MIN_TEMPLATE_ENTRY_ID_INT):
            continue
        if int(tid) not in template_entry_ids:
            missing_template_refs.append(
                {"instance_id_int": _extract_instance_id_int(rec), "template_id_int": int(tid)}
            )
            if len(missing_template_refs) >= int(max_issues):
                break

    if missing_template_refs:
        issues.append(
            IntegrityIssue(
                kind="instance_ref_missing_template_entry",
                message="发现实例引用的 template_id_int 在 root4/4/1 中不存在。",
                context={"samples": missing_template_refs[:20], "missing_total": int(len(missing_template_refs))},
            )
        )

    defs, atts = _iter_root27_defs_and_atts(payload_root)
    def_ids = {int(x) for x in (_extract_root27_def_id_int(d) for d in defs) if isinstance(x, int) and int(x) > 0}

    missing_parent_instances: List[Dict[str, Any]] = []
    missing_def_refs: List[Dict[str, Any]] = []
    for att in atts:
        meta_list = _as_list_allow_scalar(att.get(META_LIST_KEY))
        parent_id = _extract_meta40_parent_id_int(meta_list)
        if isinstance(parent_id, int) and int(parent_id) > 0 and int(parent_id) not in instance_ids:
            missing_parent_instances.append({"parent_instance_id_int": int(parent_id)})
        def_id = _extract_root27_attachment_def_id_int(att)
        if isinstance(def_id, int) and int(def_id) > 0 and int(def_id) not in def_ids:
            missing_def_refs.append({"def_id_int": int(def_id), "parent_instance_id_int": parent_id})
        if len(missing_parent_instances) + len(missing_def_refs) >= int(max_issues):
            break

    if missing_parent_instances:
        issues.append(
            IntegrityIssue(
                kind="root27_attachment_parent_instance_missing",
                message="发现 root27.2 attachment 的 parent_instance_id 不存在于 root5/root8。",
                context={"samples": missing_parent_instances[:20], "missing_total": int(len(missing_parent_instances))},
            )
        )
    if missing_def_refs:
        issues.append(
            IntegrityIssue(
                kind="root27_attachment_def_missing",
                message="发现 root27.2 attachment 引用的 def_id 不存在于 root27.1 definitions。",
                context={"samples": missing_def_refs[:20], "missing_total": int(len(missing_def_refs))},
            )
        )

    issues.extend(_check_root6_template_tabs(payload_root))

    report = {
        "input_gil": str(p),
        "summary": {
            "template_entry_ids_total": int(len(template_entry_ids)),
            "instance_ids_total": int(len(instance_ids)),
            "root27_defs_total": int(len(def_ids)),
            "root27_atts_total": int(len(atts)),
            "issues_total": int(len(issues)),
            "issues_truncated": bool(len(issues) >= int(max_issues)),
        },
        "issues": [{"kind": it.kind, "message": it.message, "context": dict(it.context)} for it in issues[: int(max_issues)]],
    }
    return report


def _default_report_path(input_gil: Path) -> Path:
    """生成默认报告路径（落在 tmp/ 下）。"""
    stem = Path(input_gil).resolve().stem
    out_dir = (_repo_root() / "tmp" / "gil_resource_integrity").resolve()
    return out_dir / f"{stem}.report.json"


def _write_report(path: Path, report: Dict[str, Any]) -> None:
    """将报告以 UTF-8 JSON 写入磁盘。"""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    """解析参数并执行资源一致性体检脚本。"""
    parser = argparse.ArgumentParser(description="Diagnose .gil template/instance/decorations/tabs integrity.")
    parser.add_argument("--input", required=True, help="Input .gil path")
    parser.add_argument("--report", default="", help="Output report.json path (default: repo/tmp/gil_resource_integrity/<stem>.report.json)")
    parser.add_argument("--max-issues", type=int, default=int(DEFAULT_MAX_ISSUES), help="Max issues to record (default: 500)")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    sys.path.insert(0, str(repo_root / "private_extensions"))

    max_issues = int(args.max_issues)
    if max_issues <= 0:
        raise ValueError("--max-issues must be > 0")

    input_gil = Path(str(args.input))
    report = diagnose_gil_resource_integrity(input_gil=input_gil, max_issues=max_issues)

    report_path = Path(str(args.report)).resolve() if str(args.report or "").strip() != "" else _default_report_path(input_gil)
    _write_report(report_path, report)

    summary = report.get("summary") if isinstance(report, dict) else None
    summary_dict = summary if isinstance(summary, dict) else {}
    print(str(input_gil.resolve()))
    print(
        "templates="
        + str(int(summary_dict.get("template_entry_ids_total") or 0))
        + " instances="
        + str(int(summary_dict.get("instance_ids_total") or 0))
        + " root27_defs="
        + str(int(summary_dict.get("root27_defs_total") or 0))
        + " root27_atts="
        + str(int(summary_dict.get("root27_atts_total") or 0))
    )
    print("issues_total=" + str(int(summary_dict.get("issues_total") or 0)) + " truncated=" + str(bool(summary_dict.get("issues_truncated"))))
    print("report=" + str(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

