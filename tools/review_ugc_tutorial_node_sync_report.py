from __future__ import annotations

"""
review_ugc_tutorial_node_sync_report.py

目标：
- 对 tools.sync_ugc_tutorial_node_specs 生成的 diff_full.json 做“逐条人工复核辅助”：
  - changed_ports：判定哪些差异可信且建议更新；哪些差异更像文档缺失/类型过粗/不应自动降级；
  - missing_locally：判定是否可能只是本地节点别名/命名差异导致的误报；否则为“本地确实缺实现节点”；
  - extra_locally：本地存在但文档未覆盖的节点，仅做汇总，不建议据此删除/改名。

约束：
- fail-fast：不吞异常；
- 只读分析：不写回 plugins/nodes，不调用 --apply；
- 输出一份 Markdown 报告到 tmp/artifacts/ugc_tutorial_node_sync/review_diff_full.md。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_ARTIFACT_DIR = Path("tmp/artifacts/ugc_tutorial_node_sync")
DEFAULT_DIFF_JSON = "diff_full.json"
DEFAULT_UPSTREAM_JSON = "upstream_full.json"
DEFAULT_OUT_MD = "review_diff_full.md"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_dict(v: Any, where: str) -> Dict[str, Any]:
    if not isinstance(v, dict):
        raise ValueError(f"{where} is not dict")
    return v


def _ensure_list(v: Any, where: str) -> List[Any]:
    if not isinstance(v, list):
        raise ValueError(f"{where} is not list")
    return v


def _load_local_pipeline_index(workspace_root: Path) -> Dict[str, Any]:
    import sys

    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))
    from engine.nodes.pipeline.runner import run_pipeline

    index = run_pipeline(workspace_root.resolve())
    if not isinstance(index, dict):
        raise ValueError("pipeline index is not dict")
    return index


def _build_alias_lookup(index: Dict[str, Any]) -> Dict[str, str]:
    alias_to_key = index.get("alias_to_key")
    if not isinstance(alias_to_key, dict):
        raise ValueError("pipeline index missing alias_to_key")
    out: Dict[str, str] = {}
    for k, v in alias_to_key.items():
        ks = str(k or "").strip()
        vs = str(v or "").strip()
        if ks and vs:
            out[ks] = vs
    return out


@dataclass(frozen=True)
class Key:
    scope: str
    category: str
    name: str

    def category_name(self) -> str:
        return f"{self.category}/{self.name}"


def _as_key(d: Dict[str, Any]) -> Key:
    scope = str(d.get("scope") or "").strip().lower()
    category = str(d.get("category") or "").strip()
    name = str(d.get("name") or "").strip()
    if scope not in {"server", "client"}:
        raise ValueError(f"invalid scope: {scope!r}")
    if category == "" or name == "":
        raise ValueError("empty category/name in key")
    return Key(scope=scope, category=category, name=name)


def _diff_kind_for_changed_ports(item: Dict[str, Any]) -> str:
    """
    给 changed_ports 打粗分类（只用于审阅/排序）：
    - doc_missing_table: doc_data_inputs/doc_data_outputs 为空（或明显不完整）
    - doc_coarse_types: doc 使用 泛型/字典/枚举 等过粗类型，而本地使用更精细别名
    - doc_add_or_remove_ports: 端口数量不同且 doc 非空
    - doc_rename_port: 端口名不同但数量相近（需要人工核对）
    - other
    """
    local_in = item.get("local_data_inputs") or []
    doc_in = item.get("doc_data_inputs") or []
    local_out = item.get("local_data_outputs") or []
    doc_out = item.get("doc_data_outputs") or []

    if (isinstance(doc_in, list) and len(doc_in) == 0) and (isinstance(doc_out, list) and len(doc_out) == 0):
        return "doc_missing_table"

    def _has_coarse(doc_ports: Any) -> bool:
        if not isinstance(doc_ports, list):
            return False
        for p in doc_ports:
            if not isinstance(p, (list, tuple)) or len(p) != 2:
                continue
            t = str(p[1] or "")
            if t in {"泛型", "字典"}:
                return True
        return False

    if _has_coarse(doc_in) or _has_coarse(doc_out):
        return "doc_coarse_types"

    if isinstance(local_in, list) and isinstance(doc_in, list) and len(local_in) != len(doc_in):
        return "doc_add_or_remove_ports"
    if isinstance(local_out, list) and isinstance(doc_out, list) and len(local_out) != len(doc_out):
        return "doc_add_or_remove_ports"

    # 端口数量相同但名字不同，常见于文档改名/本地别名未同步
    if isinstance(local_in, list) and isinstance(doc_in, list) and len(local_in) == len(doc_in) and local_in != doc_in:
        return "doc_rename_port"
    if isinstance(local_out, list) and isinstance(doc_out, list) and len(local_out) == len(doc_out) and local_out != doc_out:
        return "doc_rename_port"

    return "other"


def _recommendation_for_changed_ports(item: Dict[str, Any]) -> str:
    kind = _diff_kind_for_changed_ports(item)
    if kind == "doc_missing_table":
        return "不建议更新：文档未提供参数表/抓取为空，无法证明本地端口定义错误"
    if kind == "doc_coarse_types":
        return "不建议自动更新：文档类型过粗（泛型/字典），本地更精细；需人工确认是否要降级"
    if kind == "doc_add_or_remove_ports":
        return "建议更新：文档端口数量变化且参数表完整（注意：仅改@node_spec会暴露实现未跟上的错误）"
    if kind == "doc_rename_port":
        return "需人工确认：疑似端口改名/顺序变化，建议先确认是否应使用 port_aliases 兼容"
    return "需人工确认：差异形态不典型"


def _md_escape(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _write_report(
    *,
    out_path: Path,
    summary: Dict[str, Any],
    changed_ports: List[Dict[str, Any]],
    missing_locally: List[Dict[str, Any]],
    extra_locally: List[Dict[str, Any]],
    alias_to_key: Dict[str, str],
) -> None:
    lines: List[str] = []
    lines.append("## UGC 教程节点同步报告（人工复核版）")
    lines.append("")
    lines.append("### 汇总")
    lines.append(f"- **missing_locally**: {int(summary.get('missing_locally') or 0)}")
    lines.append(f"- **extra_locally**: {int(summary.get('extra_locally') or 0)}")
    lines.append(f"- **changed_ports**: {int(summary.get('changed_ports') or 0)}")
    lines.append("")

    lines.append("### changed_ports（逐条建议）")
    lines.append("")
    lines.append("| scope | category | name | kind | 建议 | local_file |")
    lines.append("|---|---|---|---|---|---|")
    for it in changed_ports:
        key = _as_key(_ensure_dict(it.get("key") or {}, "changed_ports[i].key"))
        kind = _diff_kind_for_changed_ports(it)
        rec = _recommendation_for_changed_ports(it)
        local_file = str(it.get("local_file_path") or "")
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape(key.scope),
                    _md_escape(key.category),
                    _md_escape(key.name),
                    _md_escape(kind),
                    _md_escape(rec),
                    _md_escape(local_file),
                ]
            )
            + " |"
        )
    lines.append("")

    lines.append("### missing_locally（是否可能是别名误报）")
    lines.append("")
    lines.append("| scope | category | name | alias_hit | alias_mapped_key | 结论 |")
    lines.append("|---|---|---|---|---|---|")
    for it in missing_locally:
        key = _as_key(it)
        alias_key = key.category_name()
        mapped = alias_to_key.get(alias_key, "")
        hit = "yes" if mapped else "no"
        conclusion = "疑似别名/命名差异（本地可能已存在）" if mapped else "本地确实缺实现节点（不建议自动补文件）"
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape(key.scope),
                    _md_escape(key.category),
                    _md_escape(key.name),
                    hit,
                    _md_escape(mapped),
                    _md_escape(conclusion),
                ]
            )
            + " |"
        )
    lines.append("")

    lines.append("### extra_locally（仅汇总）")
    lines.append("")
    lines.append("- 说明：本地存在但文档未覆盖不代表有问题；不建议据此删除/降级。")
    lines.append(f"- extra_locally_count: {len(extra_locally)}")
    lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="对 diff_full.json 做逐条审阅辅助，生成 Markdown 复核报告。")
    parser.add_argument("--workspace-root", default=None, help="工程根目录（默认按本文件位置推断）")
    parser.add_argument("--artifact-dir", default=None, help="diff/upstream 所在目录（默认 tmp/artifacts/ugc_tutorial_node_sync）")
    parser.add_argument("--diff-json", default=DEFAULT_DIFF_JSON)
    parser.add_argument("--upstream-json", default=DEFAULT_UPSTREAM_JSON)
    parser.add_argument("--out-md", default=DEFAULT_OUT_MD)
    args = parser.parse_args(list(argv) if argv is not None else None)

    workspace_root = Path(args.workspace_root).resolve() if args.workspace_root else _repo_root().resolve()
    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else (workspace_root / DEFAULT_ARTIFACT_DIR).resolve()
    diff_path = (artifact_dir / str(args.diff_json)).resolve()
    upstream_path = (artifact_dir / str(args.upstream_json)).resolve()
    out_path = (artifact_dir / str(args.out_md)).resolve()

    if not diff_path.is_file():
        raise FileNotFoundError(str(diff_path))
    if not upstream_path.is_file():
        raise FileNotFoundError(str(upstream_path))

    diff_doc = _ensure_dict(_read_json(diff_path), "diff_full.json")
    summary = _ensure_dict(diff_doc.get("summary") or {}, "diff_full.json.summary")
    changed_ports = _ensure_list(diff_doc.get("changed_ports") or [], "diff_full.json.changed_ports")
    missing_locally = _ensure_list(diff_doc.get("missing_locally") or [], "diff_full.json.missing_locally")
    extra_locally = _ensure_list(diff_doc.get("extra_locally") or [], "diff_full.json.extra_locally")

    # 读取 upstream 以确保“全量爬取”确实存在（避免只对比本地索引的误解）
    upstream_nodes = _ensure_list(_read_json(upstream_path), "upstream_full.json")
    if len(upstream_nodes) == 0:
        raise ValueError("upstream_full.json is empty; refuse to review")

    index = _load_local_pipeline_index(workspace_root)
    alias_to_key = _build_alias_lookup(index)

    _write_report(
        out_path=out_path,
        summary=summary,
        changed_ports=changed_ports,
        missing_locally=missing_locally,
        extra_locally=extra_locally,
        alias_to_key=alias_to_key,
    )

    print("=" * 80)
    print("复核报告已生成：")
    print(f"- diff_json: {str(diff_path)}")
    print(f"- upstream_json: {str(upstream_path)}")
    print(f"- out_md: {str(out_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

