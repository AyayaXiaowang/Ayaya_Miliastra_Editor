from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .constants import SCAN_HEAD_CHARS, UI_KEY_PLACEHOLDER_RE, UI_SOURCE_HTML_HINT_RE


def _infer_required_ui_layout_names_from_graph_code_files(*, graph_code_files: Sequence[Path]) -> set[str]:
    """
    从 Graph Code 的头部 docstring/注释里推断“UI 页面名（HTML stem）”，用于选择合适的 UI 导出记录：

    - 典型写法（见第七关 UI 图）：
      `配套 管理配置/UI源码/第七关-游戏中.html 的交互...`
    """
    out: set[str] = set()
    for p in list(graph_code_files or []):
        path = Path(p).resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        head = path.read_text(encoding="utf-8")[: int(SCAN_HEAD_CHARS)]
        for m in UI_SOURCE_HTML_HINT_RE.finditer(head):
            name = str(m.group(1) or "").strip()
            if name != "":
                out.add(name)
    return out


def _collect_required_ui_keys_from_graph_code_files(*, graph_code_files: Sequence[Path]) -> set[str]:
    """
    从 Graph Code 源码中直接提取 `ui_key:` / `ui:` 占位符使用到的 key 文本。

    目的：
    - 在 `--ui-export-record latest` 场景下，自动选择一个“快照内确实包含这些 key”的 UI 导出记录；
    - 避免 latest 记录存在但快照覆盖不全（例如只导出了部分页面或 registry 被去重导致 key 消失），进而写回阶段报缺 key。
    """
    out: set[str] = set()
    for p in list(graph_code_files or []):
        path = Path(p).resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        text = path.read_text(encoding="utf-8")
        for m in UI_KEY_PLACEHOLDER_RE.finditer(text):
            k = str(m.group("key") or "").strip()
            if k != "":
                out.add(k)
    return out


# === Public facade (stable, cross-module) ===
#
# NOTE:
# - External modules must not import underscored private helpers from this module.
# - Keep these wrappers stable; internal implementations may evolve freely.


def collect_required_ui_keys_from_graph_code_files(*, graph_code_files: Sequence[Path]) -> set[str]:
    return _collect_required_ui_keys_from_graph_code_files(graph_code_files=graph_code_files)

