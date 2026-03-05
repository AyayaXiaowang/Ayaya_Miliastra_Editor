from __future__ import annotations

"""UI 会话状态读写工具。

职责：
- 将主窗口当前的视图模式与关键选中上下文序列化为 JSON；
- 将 JSON 反序列化为字典供 UI 层自行解释与恢复。

设计约定：
- 状态文件位于 `<runtime_cache_root>/ui_last_session.json`（默认 runtime_cache_root 为 app/runtime/cache，可通过 settings.RUNTIME_CACHE_ROOT 配置）；
- 仅存放轻量级 UI 状态（视图模式、选中 ID 与少量上下文），
  不包含任何大体量资源或节点图数据；
- 解析失败时允许直接抛出异常，由调用方决定是否中止启动，
  不在本模块吞掉错误。
"""

from pathlib import Path
from typing import Any, Dict, Optional

from app.runtime.services import get_shared_json_cache_service
from engine.utils.cache.cache_paths import get_runtime_cache_root


_SESSION_FILENAME = "ui_last_session.json"


def get_ui_session_state_path(workspace_path: Path) -> Path:
    """返回 UI 会话状态文件路径。

    参数：
        workspace_path: 工程根路径（workspace_root）。
    """
    return get_runtime_cache_root(workspace_path) / _SESSION_FILENAME


def load_last_session_state(workspace_path: Path) -> Optional[Dict[str, Any]]:
    """从磁盘加载上一次 UI 会话状态。

    - 文件不存在或内容为空时返回 None；
    - 若内容不是 JSON 对象，则同样返回 None。
    """
    cache_service = get_shared_json_cache_service(workspace_path)
    return cache_service.load_document_dict(_SESSION_FILENAME)


def save_last_session_state(workspace_path: Path, state_data: Dict[str, Any]) -> None:
    """将当前 UI 会话状态写入磁盘。

    - 会自动创建 runtime_cache_root 目录；
    - 使用 UTF-8 与缩进/排序格式保存，便于人工检查与调试。
    """
    cache_service = get_shared_json_cache_service(workspace_path)
    cache_service.save_document_dict(_SESSION_FILENAME, state_data)


