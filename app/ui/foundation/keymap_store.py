from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.runtime.services import get_shared_json_cache_service

_KEYMAP_FILENAME = "ui_keymap.json"
_KEYMAP_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class KeymapActionSpec:
    """一条可配置快捷键的动作定义。"""

    action_id: str
    scope: str
    title: str
    description: str
    default_shortcuts: tuple[str, ...]
    max_shortcuts: int = 1


DEFAULT_KEYMAP_SPECS: tuple[KeymapActionSpec, ...] = (
    # ---- 全局（主窗口级）
    KeymapActionSpec(
        action_id="global.command_palette",
        scope="全局",
        title="全局搜索 / 命令面板",
        description="打开可搜索的命令面板，支持跳转元件/实体/预设/节点图/管理项/项目存档。",
        default_shortcuts=("Ctrl+K", "Ctrl+Shift+P", "Ctrl+E"),
        max_shortcuts=3,
    ),
    KeymapActionSpec(
        action_id="global.validate",
        scope="全局",
        title="验证项目存档",
        description="切换到验证页面并触发一次校验。",
        default_shortcuts=("F5",),
    ),
    KeymapActionSpec(
        action_id="global.dev_tools_toggle",
        scope="全局",
        title="开发者工具（悬停显示控件信息）",
        description="开启/关闭 UI 悬停检查器。",
        default_shortcuts=("F12",),
    ),
    KeymapActionSpec(
        action_id="global.app_perf_overlay_toggle",
        scope="全局",
        title="性能悬浮面板（卡顿定位）",
        description="显示/隐藏全局性能悬浮面板（点击悬浮面板可打开详情）。",
        default_shortcuts=("F11",),
    ),
    KeymapActionSpec(
        action_id="global.nav_back",
        scope="全局",
        title="后退",
        description="回放主窗口导航历史。",
        default_shortcuts=("Alt+Left",),
    ),
    KeymapActionSpec(
        action_id="global.nav_forward",
        scope="全局",
        title="前进",
        description="回放主窗口导航历史。",
        default_shortcuts=("Alt+Right",),
    ),
    # ---- 库页通用（元件/实体/战斗/节点图库）
    KeymapActionSpec(
        action_id="library.new",
        scope="库页通用（元件/实体/战斗/节点图库）",
        title="新建",
        description="新建条目（节点图库：新建节点图）。",
        default_shortcuts=("Ctrl+N",),
    ),
    KeymapActionSpec(
        action_id="library.duplicate",
        scope="库页通用（元件/实体/战斗/节点图库）",
        title="复制",
        description="复制当前选中条目。",
        default_shortcuts=("Ctrl+D",),
    ),
    KeymapActionSpec(
        action_id="library.rename",
        scope="库页通用（元件/实体/战斗/节点图库）",
        title="重命名",
        description="重命名当前选中条目。",
        default_shortcuts=("F2",),
    ),
    KeymapActionSpec(
        action_id="library.delete",
        scope="库页通用（元件/实体/战斗/节点图库）",
        title="删除",
        description="删除当前选中条目（按页面语义为“移出/物理删除”）。",
        default_shortcuts=("Delete",),
    ),
    KeymapActionSpec(
        action_id="library.move",
        scope="库页通用（元件/实体/战斗/节点图库）",
        title="移动",
        description="元件/实体/战斗预设：移动所属存档；节点图：移动到文件夹。",
        default_shortcuts=("Ctrl+M",),
    ),
    KeymapActionSpec(
        action_id="library.locate_issues",
        scope="库页通用（元件/实体/战斗/节点图库）",
        title="定位问题",
        description="跳转到验证页面并尽量定位到相关问题。",
        default_shortcuts=("Ctrl+I",),
    ),
    # ---- 画布（节点图编辑器）
    KeymapActionSpec(
        action_id="graph_view.find",
        scope="节点图画布",
        title="画布内搜索",
        description="在画布内搜索节点/连线/变量/注释等（呼出搜索浮层）。",
        default_shortcuts=("Ctrl+F",),
    ),
    KeymapActionSpec(
        action_id="graph_view.fit_all",
        scope="节点图画布",
        title="适配全图",
        description="将当前画布缩放并居中到全图可见（大图总览）。",
        default_shortcuts=("Ctrl+0",),
    ),
)

_DEFAULT_SPECS_BY_ID: dict[str, KeymapActionSpec] = {spec.action_id: spec for spec in DEFAULT_KEYMAP_SPECS}


def _normalize_shortcut_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for raw in value:
            if not isinstance(raw, str):
                continue
            text = raw.strip()
            if text:
                items.append(text)
        return items
    return []


class KeymapStore:
    """快捷键配置存储（默认值 + runtime cache 下的用户覆盖）。"""

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = Path(workspace_path).resolve()
        self._cache_service = get_shared_json_cache_service(self.workspace_path)
        self._overrides: dict[str, list[str]] = {}
        self.reload()

    # --------------------------------------------------------------------- Query
    @staticmethod
    def list_default_specs() -> tuple[KeymapActionSpec, ...]:
        return DEFAULT_KEYMAP_SPECS

    @staticmethod
    def get_default_spec(action_id: str) -> KeymapActionSpec | None:
        return _DEFAULT_SPECS_BY_ID.get(str(action_id or "").strip())

    @staticmethod
    def get_default_shortcuts(action_id: str) -> list[str]:
        spec = KeymapStore.get_default_spec(action_id)
        return list(spec.default_shortcuts) if spec is not None else []

    def get_shortcuts(self, action_id: str) -> list[str]:
        action_key = str(action_id or "").strip()
        if not action_key:
            return []
        if action_key in self._overrides:
            return list(self._overrides[action_key])
        return self.get_default_shortcuts(action_key)

    def get_primary_shortcut(self, action_id: str) -> str:
        shortcuts = self.get_shortcuts(action_id)
        return shortcuts[0] if shortcuts else ""

    def format_shortcuts_for_display(self, action_id: str) -> str:
        shortcuts = self.get_shortcuts(action_id)
        return " / ".join(shortcuts) if shortcuts else ""

    # --------------------------------------------------------------------- Mutate
    def set_shortcuts(self, action_id: str, shortcuts: Iterable[str]) -> None:
        action_key = str(action_id or "").strip()
        if not action_key:
            return
        normalized = _normalize_shortcut_list(list(shortcuts))
        default_shortcuts = self.get_default_shortcuts(action_key)
        if normalized == default_shortcuts:
            self._overrides.pop(action_key, None)
            return
        self._overrides[action_key] = normalized

    def reset_to_defaults(self) -> None:
        self._overrides.clear()

    # --------------------------------------------------------------------- Persistence
    def reload(self) -> None:
        loaded = self._cache_service.load_json(_KEYMAP_FILENAME)
        values: dict[str, Any] = {}
        if isinstance(loaded, dict):
            values_any = loaded.get("values")
            if isinstance(values_any, dict):
                values = values_any

        overrides: dict[str, list[str]] = {}
        for key, raw_value in values.items():
            if not isinstance(key, str) or not key.strip():
                continue
            overrides[key.strip()] = _normalize_shortcut_list(raw_value)
        self._overrides = overrides

    def save(self) -> None:
        payload = {
            "schema_version": int(_KEYMAP_SCHEMA_VERSION),
            "values": dict(self._overrides),
        }
        self._cache_service.save_json(_KEYMAP_FILENAME, payload, ensure_ascii=False, indent=2, sort_keys=True)

    def save_reset_to_defaults(self) -> None:
        self.reset_to_defaults()
        self.save()


__all__ = [
    "KeymapActionSpec",
    "KeymapStore",
    "DEFAULT_KEYMAP_SPECS",
]


