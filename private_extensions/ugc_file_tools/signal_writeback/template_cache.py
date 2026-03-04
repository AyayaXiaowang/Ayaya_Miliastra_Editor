from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.repo_paths import ugc_file_tools_root


def signal_node_def_template_cache_path() -> Path:
    """
    信号写回的“node_def 基底模板”缓存文件路径。

    目的：从真源/用户提供的 `.gil` 中提取一次“无参数信号”的 3 个 node_def 样本后落盘，
    后续写回信号时可直接复用该缓存，减少对外部模板文件的依赖。
    """
    return ugc_file_tools_root() / "signal_writeback" / "_signal_node_def_templates.cache.json"


def load_cached_signal_node_def_templates() -> Optional[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    """
    返回：(send_def, listen_def, send_to_server_def)。

    - 不存在缓存文件：返回 None
    - 缓存文件存在但格式不符合预期：抛错（fail-fast）
    """
    path = signal_node_def_template_cache_path().resolve()
    if not path.is_file():
        return None

    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("signal node_def template cache 顶层必须为 dict")

    version = obj.get("version")
    if version != 1:
        raise ValueError(f"unsupported signal node_def template cache version: {version!r}")

    node_defs = obj.get("node_defs")
    if not isinstance(node_defs, dict):
        raise ValueError("signal node_def template cache 缺少 node_defs(dict)")

    send_def = node_defs.get("send")
    listen_def = node_defs.get("listen")
    server_def = node_defs.get("send_to_server")
    if not (isinstance(send_def, dict) and isinstance(listen_def, dict) and isinstance(server_def, dict)):
        raise ValueError("signal node_def template cache 的 node_defs 必须包含 send/listen/send_to_server 三个 dict")

    return dict(send_def), dict(listen_def), dict(server_def)


def save_cached_signal_node_def_templates(
    *,
    send_def: Dict[str, Any],
    listen_def: Dict[str, Any],
    send_to_server_def: Dict[str, Any],
    source_hint: str,
) -> None:
    """
    将“无参数信号”的 3 个 node_def 样本写入缓存。

    注意：该缓存属于“工具内可重复生成的沉淀”，用于减少手动选择模板的成本。
    """
    if not (isinstance(send_def, dict) and isinstance(listen_def, dict) and isinstance(send_to_server_def, dict)):
        raise TypeError("send_def/listen_def/send_to_server_def 必须为 dict")

    path = signal_node_def_template_cache_path().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "source_hint": str(source_hint or ""),
        "node_defs": {
            "send": dict(send_def),
            "listen": dict(listen_def),
            "send_to_server": dict(send_to_server_def),
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = [
    "signal_node_def_template_cache_path",
    "load_cached_signal_node_def_templates",
    "save_cached_signal_node_def_templates",
]


