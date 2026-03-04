from __future__ import annotations

import re
import zlib
from typing import Any, Dict, Iterable, Optional, Sequence

from app.runtime.engine.game_state import GameRuntime


_UI_KEY_PREFIX = "ui_key:"
_LAYOUT_INDEX_KEY_PREFIX = "LAYOUT_INDEX__HTML__"


_LAYOUT_INDEX_DESC_HTML_RE = re.compile(r"[（(]([^（）()]+?)\.html[)）]")


def _hash32(text: str) -> int:
    return int(zlib.adler32(text.encode("utf-8")) & 0xFFFFFFFF)


def _stable_sim_index(ui_key: str) -> int:
    """
    为本地测试生成稳定的“伪 GUID/伪索引”：
    - 保持为正整数；
    - 高位对齐到 0x4000_0000（与历史 UI GUID 风格一致，便于日志排查）；
    - 低位由 adler32 派生，确保跨进程稳定。
    """
    checksum = _hash32(ui_key)
    return int(0x40000000 | (checksum & 0x3FFFFFFF))


def extract_html_stem_from_layout_index_description(description: str) -> str:
    """从「布局索引_*」图变量的描述中提取 HTML stem（不含 `.html`）。"""
    text = str(description or "")
    m = _LAYOUT_INDEX_DESC_HTML_RE.search(text)
    if not m:
        return ""
    return str(m.group(1) or "").strip()


def stable_layout_index_from_html_stem(html_stem: str) -> int:
    """将 HTML stem 映射为稳定 layout_index（用于本地测试的多页切换）。"""
    stem = str(html_stem or "").strip()
    if not stem:
        raise ValueError("html_stem 不能为空")
    return _stable_sim_index(f"{_LAYOUT_INDEX_KEY_PREFIX}{stem}")


def _fallback_layout_index(*, variable_name: str, description: str) -> int:
    stem = extract_html_stem_from_layout_index_description(description)
    if stem:
        return stable_layout_index_from_html_stem(stem)
    return _stable_sim_index(f"LAYOUT_INDEX__VAR__{str(variable_name or '').strip()}")


class UiKeyIndexRegistry:
    """本地测试用 ui_key <-> index(伪GUID) 注册表（稳定、可逆）。"""

    def __init__(self) -> None:
        self._index_by_key: Dict[str, int] = {}
        self._key_by_index: Dict[int, str] = {}

    def ensure(self, ui_key: str) -> int:
        key = str(ui_key or "").strip()
        if not key:
            raise ValueError("ui_key 不能为空")
        existing = self._index_by_key.get(key)
        if existing is not None:
            return int(existing)

        index = _stable_sim_index(key)
        collided = self._key_by_index.get(index)
        if collided is not None and collided != key:
            raise ValueError(f"ui_key hash 冲突：{key!r} 与 {collided!r} -> {index}")

        self._index_by_key[key] = int(index)
        self._key_by_index[int(index)] = key
        return int(index)

    def try_get_index(self, ui_key: str) -> Optional[int]:
        key = str(ui_key or "").strip()
        if not key:
            return None
        value = self._index_by_key.get(key)
        return int(value) if value is not None else None

    def try_get_key(self, index: int) -> Optional[str]:
        return self._key_by_index.get(int(index))

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "ui_key_to_index": dict(self._index_by_key),
            "note": "本文件由本地测试模拟器生成：用于将 ui_key 映射到稳定的伪 GUID/索引（不代表真实游戏 GUID）。",
        }

    def keys(self) -> list[str]:
        """返回当前注册的 ui_key 列表（本地测试/调试用途）。"""
        return list(self._index_by_key.keys())


def _iter_graph_variable_entries(graph_model: object) -> Iterable[dict[str, Any]]:
    raw = getattr(graph_model, "graph_variables", None)
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _iter_graph_variable_configs(graph_module: object) -> Iterable[object]:
    raw = getattr(graph_module, "GRAPH_VARIABLES", None)
    if not isinstance(raw, list):
        return []
    return [x for x in raw if hasattr(x, "name") and hasattr(x, "variable_type")]


def _maybe_coerce_scalar_default(*, variable_type: str, default_value: object) -> object:
    vt = str(variable_type or "").strip()
    if isinstance(default_value, bool):
        return default_value
    if isinstance(default_value, (int, float, tuple, list, dict)):
        return default_value
    if default_value is None:
        return None
    if not isinstance(default_value, str):
        return default_value

    text = default_value.strip()
    if text == "":
        return default_value

    if vt in {"整数", "GUID"}:
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        return default_value
    if vt == "浮点数":
        if re.fullmatch(r"-?\d+\.\d+", text) or re.fullmatch(r"-?\d+", text):
            return float(text)
        return default_value
    return default_value


def build_ui_key_registry_from_graph(*, graph_model: object) -> UiKeyIndexRegistry:
    """从图变量默认值里收集所有 `ui_key:` 占位符并注册为稳定 index。"""
    registry = UiKeyIndexRegistry()
    for entry in _iter_graph_variable_entries(graph_model):
        default_value = entry.get("default_value")
        if not isinstance(default_value, str):
            continue
        text = default_value.strip()
        if not text.startswith(_UI_KEY_PREFIX):
            continue
        ui_key = text[len(_UI_KEY_PREFIX) :].strip()
        if ui_key:
            registry.ensure(ui_key)
    return registry


def build_ui_key_registry_from_graph_variables(*, graph_variables: Iterable[object]) -> UiKeyIndexRegistry:
    registry = UiKeyIndexRegistry()
    for cfg in graph_variables:
        default_value = getattr(cfg, "default_value", None)
        if not isinstance(default_value, str):
            continue
        text = default_value.strip()
        if not text.startswith(_UI_KEY_PREFIX):
            continue
        ui_key = text[len(_UI_KEY_PREFIX) :].strip()
        if ui_key:
            registry.ensure(ui_key)
    return registry


def _try_resolve_ui_key_placeholder_to_index(*, text: str, ui_registry: UiKeyIndexRegistry) -> int | None:
    raw = str(text or "").strip()
    if not raw.startswith(_UI_KEY_PREFIX):
        return None
    ui_key = raw[len(_UI_KEY_PREFIX) :].strip()
    if not ui_key:
        return None
    return ui_registry.ensure(ui_key)


def _resolve_ui_key_placeholders_in_value(
    *,
    value: object,
    ui_registry: UiKeyIndexRegistry,
    memo: dict[int, object],
) -> object:
    if isinstance(value, str):
        mapped = _try_resolve_ui_key_placeholder_to_index(text=value, ui_registry=ui_registry)
        return mapped if mapped is not None else value

    if isinstance(value, (bool, int, float)) or value is None:
        return value

    value_id = id(value)
    if value_id in memo:
        return memo[value_id]

    if isinstance(value, list):
        out: list[object] = []
        memo[value_id] = out
        changed = False
        for item in value:
            resolved_item = _resolve_ui_key_placeholders_in_value(value=item, ui_registry=ui_registry, memo=memo)
            if resolved_item is not item:
                changed = True
            out.append(resolved_item)
        if not changed:
            memo[value_id] = value
            return value
        return out

    if isinstance(value, tuple):
        resolved_items: list[object] = []
        changed = False
        for item in value:
            resolved_item = _resolve_ui_key_placeholders_in_value(value=item, ui_registry=ui_registry, memo=memo)
            if resolved_item is not item:
                changed = True
            resolved_items.append(resolved_item)
        if not changed:
            memo[value_id] = value
            return value
        out = tuple(resolved_items)
        memo[value_id] = out
        return out

    if isinstance(value, dict):
        out: dict[object, object] = {}
        memo[value_id] = out
        changed = False
        for key, item in value.items():
            resolved_key = _resolve_ui_key_placeholders_in_value(value=key, ui_registry=ui_registry, memo=memo)
            resolved_item = _resolve_ui_key_placeholders_in_value(value=item, ui_registry=ui_registry, memo=memo)
            if resolved_key is not key or resolved_item is not item:
                changed = True
            out[resolved_key] = resolved_item
        if not changed:
            memo[value_id] = value
            return value
        return out

    if isinstance(value, set):
        out: set[object] = set()
        memo[value_id] = out
        changed = False
        for item in value:
            resolved_item = _resolve_ui_key_placeholders_in_value(value=item, ui_registry=ui_registry, memo=memo)
            if resolved_item is not item:
                changed = True
            out.add(resolved_item)
        if not changed:
            memo[value_id] = value
            return value
        return out

    return value


def resolve_ui_key_placeholders_in_graph_module(*, graph_module: object, ui_registry: UiKeyIndexRegistry) -> None:
    """
    本地测试下直接加载 Graph Code 源码时，模块级常量中的 `ui_key:` 不会经过“写回阶段”。
    这里在挂载前做一次回填，避免节点图把占位符字符串当整数使用。
    """
    module_dict = getattr(graph_module, "__dict__", None)
    if not isinstance(module_dict, dict):
        return

    memo: dict[int, object] = {}
    for name, raw in list(module_dict.items()):
        if not isinstance(name, str):
            continue
        if name.startswith("__") or name == "GRAPH_VARIABLES":
            continue
        if not isinstance(raw, (str, list, tuple, dict, set)):
            continue

        resolved = _resolve_ui_key_placeholders_in_value(value=raw, ui_registry=ui_registry, memo=memo)
        if resolved is raw:
            continue
        setattr(graph_module, name, resolved)


def populate_runtime_graph_variables_from_ui_constants(
    *,
    game: GameRuntime,
    graph_modules: Sequence[object],
    ui_registry: UiKeyIndexRegistry,
    notes: dict[str, Any] | None = None,
) -> None:
    """
    将“图源码模块级 UI 常量”（通常是 ui_key 占位符写回后的稳定整数索引）同步到 GameRuntime.graph_variables。

    背景：
    - 真实 Graph Code 中，很多 UI widget/group 索引会以“模块级常量”形式存在（非 GRAPH_VARIABLES）。
    - 节点图逻辑可能通过『获取节点图变量』读取这些索引，因此本地模拟需要在初始化时注入它们。

    约束：
    - 仅同步“稳定伪 GUID/索引”（高位包含 0x4000_0000）以避免把资源 ID / 音效 ID / 随机数等普通常量污染到 graph_variables。
    - 不覆盖已存在的 graph_variables（GRAPH_VARIABLES 写入优先）。
    """
    if not isinstance(getattr(game, "graph_variables", None), dict):
        game.graph_variables = {}

    injected: dict[str, int] = {}
    state_groups_by_base: dict[str, list[tuple[str, int, str]]] = {}

    for module in list(graph_modules or ()):
        module_dict = getattr(module, "__dict__", None)
        if not isinstance(module_dict, dict):
            continue
        for name, value in list(module_dict.items()):
            if not isinstance(name, str):
                continue
            if name.startswith("__") or name == "GRAPH_VARIABLES":
                continue
            if not isinstance(value, int):
                continue
            idx = int(value)
            if idx <= 0:
                continue
            # stable_sim_index: 0x4000_0000 | (adler32 & 0x3FFF_FFFF)
            if (idx & 0x40000000) != 0x40000000:
                continue

            # 尽量保证这是“UI key 派生出来的 index”（可回映射），但 layout_index 也在同一号段；
            # 此处不强制要求 registry 内可回映射：只要是稳定号段即可。
            ui_key = ui_registry.try_get_key(idx) or ""
            if ui_key.startswith("UI_STATE_GROUP__"):
                parts = ui_key.split("__")
                if len(parts) >= 4:
                    base = str(parts[1] or "").strip()
                    state = str(parts[2] or "").strip()
                    if base and state:
                        state_groups_by_base.setdefault(base, []).append((name, idx, state))

            existing = game.graph_variables.get(name, None)
            if isinstance(existing, int) and int(existing) != 0:
                # 已有非 0 值：保持 GRAPH_VARIABLES 或上游初始化的结果，避免意外覆盖。
                continue
            if existing is not None and not isinstance(existing, int):
                # 异常类型：不覆盖（留给上游定位）。
                continue
            game.graph_variables[name] = idx
            injected[name] = idx

    derived_hidden: dict[str, int] = {}
    for base, items in sorted(state_groups_by_base.items(), key=lambda kv: str(kv[0]).casefold()):
        states = {st for _n, _idx, st in items}
        need_hidden = ("show" in states) or str(base).endswith("overlay")
        if not need_hidden:
            continue
        if "hidden" in states:
            continue

        # 推断变量名前缀：优先使用 *_show组；否则使用第一个 '_' 前的片段（例如 新手教程_guide_0组 -> 新手教程）
        prefixes_show: list[str] = []
        prefixes_generic: list[str] = []
        for n, _idx, _st in items:
            if isinstance(n, str) and n.endswith("_show组"):
                prefixes_show.append(n[: -len("_show组")])
                continue
            if isinstance(n, str) and n.endswith("组") and "_" in n:
                prefixes_generic.append(n.split("_", 1)[0])

        prefix = (prefixes_show[0] if prefixes_show else (prefixes_generic[0] if prefixes_generic else "")).strip()
        if not prefix:
            continue

        hidden_name = f"{prefix}_hidden组"
        existing_hidden = game.graph_variables.get(hidden_name, None)
        if isinstance(existing_hidden, int) and int(existing_hidden) != 0:
            continue
        if existing_hidden is not None and not isinstance(existing_hidden, int):
            continue

        hidden_key = f"UI_STATE_GROUP__{base}__hidden__group"
        hidden_idx = int(ui_registry.ensure(hidden_key))
        game.graph_variables[hidden_name] = hidden_idx
        derived_hidden[hidden_name] = hidden_idx

    if notes is not None:
        notes["injected_ui_constants_count"] = int(len(injected))
        if injected:
            # 只记录 key 列表，避免把大量 index 常量塞进 notes 导致面板卡顿。
            notes["injected_ui_constants"] = sorted(list(injected.keys()))
        notes["derived_ui_hidden_constants_count"] = int(len(derived_hidden))
        if derived_hidden:
            notes["derived_ui_hidden_constants"] = sorted(list(derived_hidden.keys()))


def populate_runtime_graph_variables_from_graph_variables(
    *,
    game: GameRuntime,
    graph_variables: Iterable[object],
    ui_registry: UiKeyIndexRegistry,
    enable_layout_index_fallback: bool,
    notes: dict[str, Any] | None = None,
) -> None:
    """
    将节点图源码中的 GRAPH_VARIABLES.default_value 写入 GameRuntime.graph_variables。
    用途与约束同 populate_runtime_graph_variables（但数据源为 GraphVariableConfig 列表）。
    """
    if not isinstance(getattr(game, "graph_variables", None), dict):
        game.graph_variables = {}

    layout_fallbacks: dict[str, int] = {}
    for cfg in graph_variables:
        name = str(getattr(cfg, "name", "") or "").strip()
        if not name:
            continue
        variable_type = str(getattr(cfg, "variable_type", "") or "").strip()
        default_value = getattr(cfg, "default_value", None)
        description = str(getattr(cfg, "description", "") or "")

        if isinstance(default_value, str):
            text = default_value.strip()
            if text.startswith(_UI_KEY_PREFIX):
                ui_key = text[len(_UI_KEY_PREFIX) :].strip()
                if ui_key:
                    game.graph_variables[name] = ui_registry.ensure(ui_key)
                    continue

        value = _maybe_coerce_scalar_default(variable_type=variable_type, default_value=default_value)

        if (
            enable_layout_index_fallback
            and str(name).startswith("布局索引_")
            and variable_type == "整数"
            and value == 0
        ):
            fallback = _fallback_layout_index(variable_name=name, description=description)
            game.graph_variables[name] = fallback
            layout_fallbacks[str(name)] = int(fallback)
            continue

        game.graph_variables[name] = value

    if notes is not None and layout_fallbacks:
        notes["layout_index_fallbacks"] = dict(layout_fallbacks)


def populate_runtime_graph_variables(
    *,
    game: GameRuntime,
    graph_model: object,
    ui_registry: UiKeyIndexRegistry,
    enable_layout_index_fallback: bool,
    notes: dict[str, Any] | None = None,
) -> None:
    """
    将 GraphModel.graph_variables 的 default_value 写入 GameRuntime.graph_variables。

    说明：
    - 本函数用于“本地测试”初始化，不应产生大量日志，因此不走 set_graph_variable 的打印路径；
    - `ui_key:` 形式会在此处解析为稳定 index（伪 GUID）；
    - 布局索引（布局索引_*）若默认值为 0，且启用 fallback，则填入 1（让图逻辑能继续跑）。
    """
    if not isinstance(getattr(game, "graph_variables", None), dict):
        game.graph_variables = {}

    layout_fallbacks: dict[str, int] = {}
    for entry in _iter_graph_variable_entries(graph_model):
        name = str(entry.get("name") or "").strip()
        if not name:
            continue

        variable_type = str(entry.get("variable_type") or "").strip()
        default_value = entry.get("default_value", None)

        # ui_key:... -> 伪 GUID index
        if isinstance(default_value, str):
            text = default_value.strip()
            if text.startswith(_UI_KEY_PREFIX):
                ui_key = text[len(_UI_KEY_PREFIX) :].strip()
                if ui_key:
                    game.graph_variables[name] = ui_registry.ensure(ui_key)
                    continue

        value = _maybe_coerce_scalar_default(variable_type=variable_type, default_value=default_value)
        description = str(entry.get("description") or "")

        # 布局索引（写回阶段会回填，MVP 本地测试给个非 0 兜底，让逻辑不因“索引=0”短路）
        if (
            enable_layout_index_fallback
            and str(name).startswith("布局索引_")
            and variable_type == "整数"
            and value == 0
        ):
            fallback = _fallback_layout_index(variable_name=name, description=description)
            game.graph_variables[name] = fallback
            layout_fallbacks[str(name)] = int(fallback)
            continue

        game.graph_variables[name] = value

    if notes is not None and layout_fallbacks:
        notes["layout_index_fallbacks"] = dict(layout_fallbacks)


__all__ = [
    "UiKeyIndexRegistry",
    "extract_html_stem_from_layout_index_description",
    "stable_layout_index_from_html_stem",
    "build_ui_key_registry_from_graph",
    "build_ui_key_registry_from_graph_variables",
    "resolve_ui_key_placeholders_in_graph_module",
    "populate_runtime_graph_variables_from_ui_constants",
    "populate_runtime_graph_variables_from_graph_variables",
    "populate_runtime_graph_variables",
]

