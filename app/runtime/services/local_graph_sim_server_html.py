from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from app.runtime.services.local_graph_simulator import stable_layout_index_from_html_stem

_INJECT_SCRIPT_MARKER = "</body>"

_UI_DEFAULTS_ATTR_RE = re.compile(r"data-ui-variable-defaults\s*=\s*'([\s\S]*?)'", flags=re.IGNORECASE)


def _inject_local_sim_script(html_text: str) -> str:
    """向 UI HTML 注入本地测试脚本（/local_sim.js）。"""
    text = str(html_text or "")
    injection = "\n<script src=\"/local_sim.js\"></script>\n"
    if _INJECT_SCRIPT_MARKER in text:
        return text.replace(_INJECT_SCRIPT_MARKER, injection + _INJECT_SCRIPT_MARKER, 1)
    return text + injection


def _extract_lv_defaults_from_ui_html(html_text: str) -> dict[str, Any]:
    """从 UI HTML 的 `data-ui-variable-defaults` 中提取 lv.* 默认值。

    返回的 key 为去掉 `lv.` 前缀后的变量名（例如 `UI战斗_文本`）。
    """
    text = str(html_text or "")
    m = _UI_DEFAULTS_ATTR_RE.search(text)
    if not m:
        return {}
    raw = str(m.group(1) or "").strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("data-ui-variable-defaults 必须为 JSON 对象")

    out: dict[str, Any] = {}
    for k, v in payload.items():
        if not isinstance(k, str):
            continue
        key = k.strip()
        if not key.startswith("lv."):
            continue
        var_name = key[len("lv.") :].strip()
        if not var_name:
            continue
        out[var_name] = v
    return out


def _parse_int(text: str) -> int | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return int(raw)
    return None


def _build_layout_html_map(ui_html_file: Path) -> dict[int, Path]:
    """扫描 UI源码 同目录下所有 HTML，并构建 layout_index -> HTML 文件 映射。"""
    ui_file = Path(ui_html_file).resolve()
    ui_dir = ui_file.parent
    out: dict[int, Path] = {}
    for html_file in sorted(ui_dir.glob("*.html"), key=lambda p: p.name):
        idx = stable_layout_index_from_html_stem(html_file.stem)
        out[int(idx)] = html_file.resolve()
    # 确保入口文件一定存在（即便目录扫描被过滤）
    out[int(stable_layout_index_from_html_stem(ui_file.stem))] = ui_file
    return out


def _deep_merge_missing(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """深度合并（只补缺，不覆盖已有值）。

    设计目的：同目录多页面 UI 会各自提供 `data-ui-variable-defaults`。
    - 以入口 HTML 的默认值为准（不被其它页面覆盖）；
    - 其它页面仅用于“补齐缺失结构”，避免跨页切换后节点图写回 dict key 变成 no-op。
    """
    for k, v in (src or {}).items():
        if k not in dst:
            dst[k] = copy.deepcopy(v)
            continue
        dv = dst.get(k)
        if isinstance(dv, dict) and isinstance(v, dict):
            _deep_merge_missing(dv, v)
    return dst


def _extract_merged_lv_defaults(*, entry_ui_file: Path, layout_html_by_index: dict[int, Path]) -> dict[str, Any]:
    """从同目录所有 layout HTML 深度合并 `lv.*` 默认值（入口优先）。"""
    entry = Path(entry_ui_file).resolve()

    merged: dict[str, Any] = {}
    entry_defaults = _extract_lv_defaults_from_ui_html(entry.read_text(encoding="utf-8"))
    if entry_defaults:
        merged = copy.deepcopy(entry_defaults)

    for _idx, html_file in sorted((layout_html_by_index or {}).items(), key=lambda kv: (int(kv[0]), str(kv[1]))):
        p = Path(html_file).resolve()
        if p == entry:
            continue
        if not p.is_file():
            continue
        d = _extract_lv_defaults_from_ui_html(p.read_text(encoding="utf-8"))
        if d:
            _deep_merge_missing(merged, d)
    return merged

