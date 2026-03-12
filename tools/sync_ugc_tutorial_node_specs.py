from __future__ import annotations

"""
sync_ugc_tutorial_node_specs.py

目标：
- 从米哈游 UGC 教程站点“节点介绍”栏目爬取节点文档（节点名 + 参数表），并结构化导出；
- 与本仓库的实现节点库（plugins/nodes/** 的 @node_spec）做对比，输出差异报告；
- 可选 --apply：仅自动改写节点实现文件中的 @node_spec(inputs/outputs) 列表，使端口定义对齐文档。

注意：
- 本脚本只同步“节点定义（端口名/端口类型/输入输出方向）”，不会自动改写节点实现函数体逻辑；
  若同步后运行时报 TypeError/逻辑不匹配，应按文档补齐实现逻辑，保持失败显性暴露。
- fail-fast：不吞异常；解析/匹配失败会直接抛错，便于尽快定位站点结构变化或本地节点不一致。
"""

import argparse
import ast
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from tools.ugc_tutorial_node_sync.html_utils import (
    DOC_PARAM_TABLE_HEADERS,
    extract_h1_h2_titles,
    extract_text_by_tag,
    iter_tables,
    normalize_doc_type,
    strip_heading_index,
    try_parse_param_table_rows,
)
from tools.ugc_tutorial_node_sync.diff_utils import compute_diff as _compute_diff_impl
from tools.ugc_tutorial_node_sync.diff_utils import is_flow_port as _is_flow_port_impl
from tools.ugc_tutorial_node_sync.node_spec_patcher import patch_node_spec_ports_in_file

USER_AGENT = "Graph_Generater/ugc_tutorial_node_specs_sync (+https://act.mihoyo.com/)"
TIMEOUT_SECONDS = 30

GAME_BIZ = "hk4eugc_cn"
LANG = "zh-cn"

CATALOG_URL = f"https://act-webstatic.mihoyo.com/ugc-tutorial/knowledge/cn/{LANG}/catalog.json?game_biz={GAME_BIZ}&lang={LANG}"
CONTENT_URL_PREFIX = f"https://act-webstatic.mihoyo.com/ugc-tutorial/knowledge/cn/{LANG}"
CONTENT_VERSION = "1016"

CATALOG_NODES_ROOT_TITLE = "节点介绍"
CATALOG_SERVER_TITLE = "服务器节点"
CATALOG_CLIENT_TITLE = "客户端节点"

DOC_PARAM_DIR_IN = "入参"
DOC_PARAM_DIR_OUT = "出参"

FLOW_PORT_TYPE = "流程"


@dataclass(frozen=True)
class DocPortRow:
    direction: str  # 入参/出参
    name: str
    port_type: str
    description: str


@dataclass(frozen=True)
class DocNodeSpec:
    scope: str  # server/client（从 catalog branch 推断）
    category: str  # 执行节点/事件节点/查询节点/运算节点/流程控制节点/其它节点...
    name: str  # 节点名（去掉序号前缀）
    inputs: List[Tuple[str, str]]  # [(端口名, 类型)]
    outputs: List[Tuple[str, str]]
    source_path_id: str  # catalog path_id


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_out_dir(repo_root: Path) -> Path:
    return (repo_root / "tmp" / "artifacts" / "ugc_tutorial_node_sync").resolve()


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        raw = resp.read()
        content_type = str(resp.headers.get("Content-Type") or "")
        lower_ct = content_type.lower()
        if "charset=" in lower_ct:
            charset = lower_ct.split("charset=", 1)[1].split(";", 1)[0].strip()
            if charset == "":
                raise RuntimeError(f"Empty charset in Content-Type: {content_type!r} for url={url!r}")
            return raw.decode(charset)
        return raw.decode("utf-8")


def _load_json(url: str) -> Any:
    return json.loads(_fetch_text(url))


def _walk_catalog_items(items: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError("catalog.json top-level is not a list")
    stack: List[Any] = list(items)
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        yield cur
        children = cur.get("children")
        if isinstance(children, list) and len(children) > 0:
            stack.extend(children)


def _find_catalog_node_by_title(catalog: Any, title: str) -> Dict[str, Any]:
    for item in _walk_catalog_items(catalog):
        if str(item.get("title") or "") == title:
            return item
    raise KeyError(f"catalog node not found by title={title!r}")


def _collect_leaf_pages(root: Dict[str, Any]) -> List[Dict[str, Any]]:
    leaves: List[Dict[str, Any]] = []
    stack: List[Any] = [root]
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        children = cur.get("children")
        if isinstance(children, list) and len(children) > 0:
            stack.extend(children)
            continue
        leaves.append(cur)
    return leaves


def _content_url(path_id: str) -> str:
    pid = str(path_id).strip()
    if pid == "":
        raise ValueError("empty path_id")
    return f"{CONTENT_URL_PREFIX}/{pid}/content.html?v={CONTENT_VERSION}&game_biz={GAME_BIZ}&lang={LANG}"


def _parse_doc_node_specs_from_page(
    *,
    html: str,
    scope: str,
    category: str,
    path_id: str,
    wanted_node_names: Optional[set[str]],
) -> List[DocNodeSpec]:
    # 把页面按 <h2> 节点标题切成块：每个 h2 段落里找到其后的第一个参数表 table
    # 注意：执行节点/查询节点等页面一般包含大量节点；切块必须稳定。
    blocks = re.split(r"(<h2\b[\s\S]*?</h2>)", html, flags=re.IGNORECASE)
    specs: List[DocNodeSpec] = []

    current_title = ""
    for part in blocks:
        if part.lower().startswith("<h2"):
            title_texts = extract_text_by_tag(part, "h2")
            current_title = strip_heading_index(title_texts[0] if title_texts else "")
            continue
        if current_title == "":
            continue
        if wanted_node_names is not None and current_title not in wanted_node_names:
            current_title = ""
            continue

        # 在该块内找到“节点参数表”（含固定表头）。注意：块内可能存在其他 table（例如配置表/示例表）。
        rows: Optional[List[Tuple[str, str, str, str]]] = None
        for t in iter_tables(part):
            rows = try_parse_param_table_rows(t)
            if rows is not None:
                break
        if rows is None:
            continue

        # 丢弃表头行（必须精确匹配）
        filtered = [r for r in rows if tuple(r) != DOC_PARAM_TABLE_HEADERS]
        inputs: List[Tuple[str, str]] = []
        outputs: List[Tuple[str, str]] = []
        last_direction = ""

        for direction, name, port_type, _desc in filtered:
            d = str(direction or "").strip()
            if d == "" and last_direction != "":
                # 站点参数表常用 rowspan：后续行的“参数类型(入参/出参)”列会留空
                d = last_direction
            if d != "":
                last_direction = d
            n = str(name or "").strip()
            # 有些节点的参数表会带一个“空行”（全空 td）作为间隔；这里直接跳过，避免误判。
            if n == "":
                continue
            pt = str(port_type or "").strip()
            if pt == "" and n.startswith("流程"):
                t = FLOW_PORT_TYPE
            else:
                if pt == "":
                    raise ValueError(
                        "Empty doc type in param table row: "
                        f"node={current_title!r}, direction={d!r}, param_name={n!r}, path_id={path_id!r}"
                    )
                t = normalize_doc_type(pt)
            if d == DOC_PARAM_DIR_IN:
                inputs.append((n, t))
            elif d == DOC_PARAM_DIR_OUT:
                outputs.append((n, t))

        specs.append(
            DocNodeSpec(
                scope=scope,
                category=category,
                name=current_title,
                inputs=inputs,
                outputs=outputs,
                source_path_id=path_id,
            )
        )
        current_title = ""

    return specs


def _load_upstream_doc_specs(*, scope_filter: str, category_filter: str) -> List[Tuple[str, str, str]]:
    """
    返回需要下载的 (scope, category_title, path_id) 列表。
    先做 catalog 精确筛选，避免无谓下载所有页面导致运行过慢。
    """
    catalog = _load_json(CATALOG_URL)

    nodes_root = _find_catalog_node_by_title(catalog, CATALOG_NODES_ROOT_TITLE)
    nodes_children = nodes_root.get("children", [])
    server_root = _find_catalog_node_by_title(nodes_children, CATALOG_SERVER_TITLE)
    client_root = _find_catalog_node_by_title(nodes_children, CATALOG_CLIENT_TITLE)

    scope_text = str(scope_filter or "").strip().lower()
    category_text = str(category_filter or "").strip()

    leaf_pages: List[Tuple[str, Dict[str, Any]]] = []
    if scope_text in {"", "server"}:
        for leaf in _collect_leaf_pages(server_root):
            leaf_pages.append(("server", leaf))
    if scope_text in {"", "client"}:
        for leaf in _collect_leaf_pages(client_root):
            leaf_pages.append(("client", leaf))

    targets: List[Tuple[str, str, str]] = []
    for scope, leaf in leaf_pages:
        title = str(leaf.get("title") or "").strip()
        path_id = str(leaf.get("path_id") or "").strip()
        if title == "" or path_id == "":
            continue
        if category_text and title != category_text:
            continue
        targets.append((scope, title, path_id))

    if not targets:
        raise RuntimeError(f"No upstream pages matched filters: scope={scope_filter!r}, category={category_filter!r}")
    return targets


def _crawl_upstream_specs(
    *,
    scope_filter: str,
    category_filter: str,
    node_name_filter: List[str],
    extra_path_ids: List[str],
) -> List[DocNodeSpec]:
    targets = _load_upstream_doc_specs(scope_filter=scope_filter, category_filter=category_filter)

    extras = [str(x).strip() for x in list(extra_path_ids or []) if str(x).strip()]
    if extras:
        scope_text = str(scope_filter or "").strip().lower()
        category_text = str(category_filter or "").strip()
        if scope_text not in {"server", "client"} or category_text == "":
            raise ValueError("--extra-path-id requires --scope (server/client) AND --category (e.g. 执行节点)")
        for pid in extras:
            targets.append((scope_text, category_text, pid))

    # 去重（同 scope/category/path_id 只抓一次）
    seen: set[str] = set()
    deduped: List[Tuple[str, str, str]] = []
    for scope, category, pid in targets:
        key = f"{scope}|{category}|{pid}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append((scope, category, pid))

    out: List[DocNodeSpec] = []
    wanted: Optional[set[str]] = None
    if node_name_filter:
        wanted = set([strip_heading_index(str(n)) for n in node_name_filter if str(n).strip()])
    for scope, category, path_id in deduped:
        html = _fetch_text(_content_url(path_id))
        out.extend(
            _parse_doc_node_specs_from_page(
                html=html,
                scope=scope,
                category=category,
                path_id=path_id,
                wanted_node_names=wanted,
            )
        )

    if node_name_filter:
        node_set = set([strip_heading_index(str(n)) for n in node_name_filter if str(n).strip()])
        out = [s for s in out if s.name in node_set]
        if not out:
            raise RuntimeError(f"No upstream nodes matched --node filter: {sorted(list(node_set))}")
    return out


def _load_local_index(workspace_root: Path) -> Dict[str, Any]:
    if str(workspace_root) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(workspace_root))
    from engine.nodes.pipeline.runner import run_pipeline

    return run_pipeline(workspace_root.resolve())


def _build_local_by_scope_category_name(index: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    by_key = index.get("by_key")
    if not isinstance(by_key, dict):
        raise ValueError("pipeline index missing by_key dict")

    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for _key, item in by_key.items():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        category = str(item.get("category_standard") or "").strip()
        file_path = item.get("file_path")
        scopes = list(item.get("scopes") or [])
        if name == "" or category == "":
            continue
        # scope 推断以 scopes 为准；若同时支持 server+client，则两份都要写入，避免对比时误报“缺失”。
        scope_candidates: List[str] = []
        for s in scopes:
            ss = str(s or "").strip()
            if ss in {"server", "client"} and ss not in scope_candidates:
                scope_candidates.append(ss)

        if len(scope_candidates) == 0:
            fp = str(file_path or "").lower()
            if "/server/" in fp or "\\server\\" in fp:
                scope_candidates = ["server"]
            elif "/client/" in fp or "\\client\\" in fp:
                scope_candidates = ["client"]

        for scope_text in scope_candidates:
            out[(scope_text, category, name)] = item
    return out


def _is_flow_port(port_name: str, port_type: str) -> bool:
    """兼容旧函数名：调用 tools.ugc_tutorial_node_sync.diff_utils.is_flow_port。"""
    return _is_flow_port_impl(port_name, port_type)


def _compute_diff(
    *,
    upstream: List[DocNodeSpec],
    local_map: Dict[Tuple[str, str, str], Dict[str, Any]],
    subset_mode: bool,
) -> Dict[str, Any]:
    """兼容旧函数名：调用 tools.ugc_tutorial_node_sync.diff_utils.compute_diff。"""
    return _compute_diff_impl(upstream=upstream, local_map=local_map, subset_mode=subset_mode)


def _patch_node_spec_ports_in_file(*, file_path: Path, new_inputs: List[Tuple[str, str]], new_outputs: List[Tuple[str, str]]) -> None:
    """兼容旧函数名：调用 tools.ugc_tutorial_node_sync.node_spec_patcher.patch_node_spec_ports_in_file。"""
    patch_node_spec_ports_in_file(file_path=file_path, new_inputs=new_inputs, new_outputs=new_outputs)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="爬取 UGC 教程站点节点参数表，并与本地 @node_spec 对比/同步。")
    parser.add_argument("--workspace-root", default=None, help="工程根目录（默认按本文件位置推断）")
    parser.add_argument("--out-dir", default=None, help="输出目录（默认写到 tmp/artifacts/ugc_tutorial_node_sync/）")
    parser.add_argument("--output-upstream-json", default="upstream_doc_specs.json", help="上游爬取结果 JSON 文件名（相对 out-dir）")
    parser.add_argument("--output-diff-json", default="diff_report.json", help="差异报告 JSON 文件名（相对 out-dir）")
    parser.add_argument("--apply", action="store_true", help="可选：写回本地节点文件，仅同步 @node_spec(inputs/outputs)（不改实现函数体）")
    parser.add_argument("--scope", default="", help="可选：仅 server/client")
    parser.add_argument("--category", default="", help="可选：仅某个类别（例如 执行节点）")
    parser.add_argument("--node", action="append", default=[], help="可选：仅同步/对比指定节点名（可重复传入）")
    parser.add_argument(
        "--extra-path-id",
        action="append",
        default=[],
        help="可选：额外抓取的教程页面 path_id（可重复）；用于抓取不在‘节点介绍’目录下、但包含节点参数表的页面。"
             "注意：使用该参数时必须同时指定 --scope 与 --category（用于给页面内节点打标签）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    workspace_root = (
        Path(args.workspace_root).resolve()
        if args.workspace_root is not None and str(args.workspace_root).strip() != ""
        else _repo_root().resolve()
    )
    out_dir = (
        Path(args.out_dir).resolve()
        if args.out_dir is not None and str(args.out_dir).strip() != ""
        else _default_out_dir(workspace_root)
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    upstream = _crawl_upstream_specs(
        scope_filter=str(args.scope or ""),
        category_filter=str(args.category or ""),
        node_name_filter=list(args.node or []),
        extra_path_ids=list(args.extra_path_id or []),
    )

    upstream_path = (out_dir / str(args.output_upstream_json)).resolve()
    upstream_path.write_text(json.dumps([s.__dict__ for s in upstream], ensure_ascii=False, indent=2), encoding="utf-8")

    index = _load_local_index(workspace_root)
    local_map = _build_local_by_scope_category_name(index)

    subset_mode = bool(str(args.scope or "").strip() or str(args.category or "").strip() or list(args.node or []))
    diff = _compute_diff(upstream=upstream, local_map=local_map, subset_mode=subset_mode)
    diff_path = (out_dir / str(args.output_diff_json)).resolve()
    diff_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 80)
    print("UGC 教程节点规格同步报告：")
    print(f"- workspace_root: {str(workspace_root)}")
    print(f"- out_dir: {str(out_dir)}")
    print(f"- upstream_json: {str(upstream_path)}")
    print(f"- diff_json: {str(diff_path)}")
    print(f"- summary: {diff.get('summary')}")
    print("=" * 80)

    if not bool(args.apply):
        return

    changed_ports = list(diff.get("changed_ports") or [])
    if not isinstance(changed_ports, list):
        raise ValueError("diff.changed_ports is not a list")

    # 写回：仅对“changed_ports”进行 @node_spec(inputs/outputs) 更新
    upstream_map = {(s.scope, s.category, s.name): s for s in upstream}
    for item in changed_ports:
        key = item.get("key") or {}
        k = (str(key.get("scope") or ""), str(key.get("category") or ""), str(key.get("name") or ""))
        spec = upstream_map.get(k)
        if spec is None:
            raise RuntimeError(f"missing upstream spec for changed key: {k}")

        local_item = local_map.get(k)
        if local_item is None:
            raise RuntimeError(f"missing local item for changed key: {k}")
        file_path = Path(str(local_item.get("file_path") or "")).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(str(file_path))

        # 组合新 inputs/outputs：保留本地的流程端口 + 追加文档里的数据端口
        local_inputs_raw = local_item.get("inputs") or []
        local_outputs_raw = local_item.get("outputs") or []
        if not isinstance(local_inputs_raw, list) or not isinstance(local_outputs_raw, list):
            raise ValueError(f"local ports are not lists: {k}")

        local_inputs_pairs = [(str(p[0]), str(p[1])) for p in local_inputs_raw]
        local_outputs_pairs = [(str(p[0]), str(p[1])) for p in local_outputs_raw]

        flow_inputs = [(n, t or FLOW_PORT_TYPE) for (n, t) in local_inputs_pairs if _is_flow_port(n, t)]
        flow_outputs = [(n, t or FLOW_PORT_TYPE) for (n, t) in local_outputs_pairs if _is_flow_port(n, t)]

        new_inputs = flow_inputs + list(spec.inputs)
        new_outputs = flow_outputs + list(spec.outputs)

        _patch_node_spec_ports_in_file(file_path=file_path, new_inputs=new_inputs, new_outputs=new_outputs)
        print(f"[APPLY] updated @node_spec ports: {k} -> {str(file_path)}")


if __name__ == "__main__":
    main()

