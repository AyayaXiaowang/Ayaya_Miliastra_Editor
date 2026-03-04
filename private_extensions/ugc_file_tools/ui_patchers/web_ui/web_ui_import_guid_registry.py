from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def normalize_ui_key(value: Any, *, fallback: str) -> str:
    key = str(value or "").strip()
    if key == "":
        key = str(fallback or "").strip()
    if key == "":
        raise ValueError("ui_key 为空：widget 缺少 ui_key 且 widget_id 为空（无法建立 GUID 映射）。")
    return key


def load_ui_guid_registry(path: Path) -> Dict[str, int]:
    from ugc_file_tools.ui.guid_registry_format import load_ui_guid_registry_mapping

    return dict(load_ui_guid_registry_mapping(Path(path)))


def save_ui_guid_registry(path: Path, ui_key_to_guid: Dict[str, int]) -> None:
    from ugc_file_tools.ui.guid_registry_format import save_ui_guid_registry as _save_ui_guid_registry

    _save_ui_guid_registry(Path(path), dict(ui_key_to_guid or {}))


_UI_KEY_COORD_SEGMENT_RE = re.compile(r"^r\d+_\d+_\d+_\d+(?:_\d+)?$")
_UI_KEY_DEGRADED_E_SEGMENT_RE = re.compile(r"^e\d+$")


def _strip_unstable_suffix_tokens_from_ui_key_parts(parts: List[str]) -> List[str]:
    """
    去掉 Workbench 导出中常见的“不稳定后缀 token”，用于生成更稳定的 alias key。

    约定：
    - `state_*` / `ui_state`：导出端用于消歧多状态/多端坐标的内部 token（节点图侧不应依赖）
    - `r123_456_789_10(_2)`：坐标后缀（极易随画布/微调漂移）
    """
    out: List[str] = []
    for p in parts:
        token = str(p or "").strip()
        if token == "":
            continue
        if _UI_KEY_COORD_SEGMENT_RE.fullmatch(token) is not None:
            continue
        if token == "ui_state" or token.startswith("state_"):
            continue
        out.append(token)
    return out


def add_html_stem_ui_key_aliases(
    ui_key_to_guid: Dict[str, int],
    *,
    html_stem: str,
    import_prefixes: Optional[List[str]] = None,
) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """
    生成 `<html_stem>_html__...` 风格的稳定 alias key，用于节点图侧引用。

    背景：
    - Web 写回阶段生成的 ui_key 可能带 `HTML导入_界面布局__` 前缀，且多状态/坐标可能附带 `state_*` / `r*` 后缀；
    - 节点图侧更希望引用 `<页面名>_html__...` 这种“页面真源前缀 + 语义 token”的 key；
    - 同次导出（UI + 节点图）时，必须保证 registry 在节点图写回前已包含这些 alias，否则会报 “缺失 ui_key”。
    """
    stem = str(html_stem or "").strip()
    if stem == "":
        return dict(ui_key_to_guid or {}), {
            "aliases_added_total": 0,
            "aliases_conflicts_total": 0,
            "note": "html_stem 为空，跳过 alias 生成",
        }

    prefixes = list(import_prefixes or ["HTML导入_界面布局__", "HTML__"])
    mapping = dict(ui_key_to_guid or {})
    added_total = 0
    conflicts: List[Dict[str, Any]] = []

    def _should_skip_key(key0: str) -> bool:
        # 不对这些“非控件 ui_key 体系”生成 alias
        if key0.startswith("UI_STATE_GROUP__"):
            return True
        if key0.startswith("LAYOUT__") or key0.startswith("LAYOUT_INDEX__"):
            return True
        # 已经是 `<stem>_html__...` 的，不再重复生成
        if "_html__" in key0 and not key0.startswith("HTML导入_"):
            return True
        return False

    for k, v in list(mapping.items()):
        key = str(k or "").strip()
        if key == "":
            continue
        guid = int(v or 0)
        if guid <= 0:
            continue
        if _should_skip_key(key):
            continue

        core = key
        for pref in prefixes:
            if core.startswith(str(pref)):
                core = core[len(str(pref)) :]
                break
        core = str(core).strip()
        if core == "":
            continue

        parts = [p for p in core.split("__") if str(p)]
        parts = _strip_unstable_suffix_tokens_from_ui_key_parts(parts)
        if not parts:
            continue

        stable_core = "__".join(parts)
        alias_key = f"{stem}_html__{stable_core}"
        prev = mapping.get(alias_key)
        if prev is None:
            mapping[alias_key] = int(guid)
            added_total += 1
        else:
            if int(prev) != int(guid):
                # 不覆盖已有值，只记录冲突；冲突通常意味着历史遗留/手工编辑导致同名 alias 指向不同 guid
                conflicts.append(
                    {
                        "alias_key": alias_key,
                        "existing_guid": int(prev),
                        "new_guid": int(guid),
                        "source_key": key,
                    }
                )

    return mapping, {
        "aliases_added_total": int(added_total),
        "aliases_conflicts_total": int(len(conflicts)),
        "aliases_conflicts": conflicts[:50],
        "html_stem": stem,
        "prefixes": prefixes,
        "note": "为 UI 写回后的 registry 生成 `<html_stem>_html__...` alias（去 state/坐标后缀），供节点图占位符稳定引用。",
    }


def _ui_key_keep_preference_sort_key(ui_key: str) -> tuple[int, int, int, int, int, int, str]:
    """
    选择同一个 GUID 的多个 ui_key 时，优先保留“更稳定、语义更强、便于节点图/代码引用”的 key。

    经验规则（越靠前越优先）：
    - 交互类：`__btn_item` / `btn_*__rect`
    - 语义类：`__rect` / `__text` / `__group`
    - 装饰类：`__rect_shadow` / `__shadow`
    - 尽量避免：坐标后缀 `__r123_456_789_10(_2)`、退化 key（例如 `e15`）
    """
    k = str(ui_key or "").strip()
    parts = [p for p in k.split("__") if str(p)]

    has_btn_item = "btn_item" in parts
    has_btn_fill = "btn_fill" in parts
    has_rect = "rect" in parts
    has_text = "text" in parts
    has_group = "group" in parts
    has_rect_shadow = "rect_shadow" in parts
    has_shadow = any(p == "shadow" or str(p).endswith("_shadow") for p in parts)
    button_related = any(str(p).startswith("btn") for p in parts)

    coord_segments_total = sum(1 for p in parts if _UI_KEY_COORD_SEGMENT_RE.fullmatch(str(p)) is not None)
    has_state_suffix = any(str(p) == "ui_state" or str(p).startswith("state_") for p in parts)
    has_degraded_e = any(_UI_KEY_DEGRADED_E_SEGMENT_RE.fullmatch(str(p)) is not None for p in parts)

    # kind_priority：越小越优先
    if k.startswith("UI_STATE_GROUP__"):
        kind_priority = 0
    elif has_btn_item:
        kind_priority = 1
    elif button_related and has_rect and not has_shadow:
        kind_priority = 2
    elif button_related and has_rect:
        kind_priority = 3
    elif button_related and has_btn_fill and not has_shadow:
        kind_priority = 4
    elif button_related and has_btn_fill:
        kind_priority = 5
    elif button_related:
        kind_priority = 6
    elif has_rect and not has_shadow:
        kind_priority = 7
    elif has_text and not has_shadow:
        kind_priority = 8
    elif has_group:
        kind_priority = 9
    elif has_rect_shadow:
        kind_priority = 10
    elif has_shadow:
        kind_priority = 11
    else:
        kind_priority = 12

    # 二级偏好：避免坐标/状态/退化 key；最后用更短的 key（通常更稳定）+ 字典序保证稳定性
    return (
        int(kind_priority),
        int(coord_segments_total),
        int(1 if has_state_suffix else 0),
        int(1 if has_degraded_e else 0),
        int(1 if has_shadow else 0),
        int(len(k)),
        str(k),
    )


def dedup_ui_guid_registry_by_guid(ui_key_to_guid: Dict[str, int]) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """
    根因修复：registry 必须满足 “GUID -> UIKey” 一对一（injective）。

    历史问题：
    - 由于 ui_key 生成规则漂移/退化（例如中文被 sanitize 成空串、退化为 e15/e30），或手工合并 registry，
      可能出现多个 ui_key 指向同一个 guid。
    - 写回端若直接信任该映射，会导致多个控件/组容器复用同一个 record：表现为“组被合并、其中一个组消失”。

    处理策略：
    - 对于同一个 guid 的多个 key：保留“更稳定、语义更强”的那个（优先交互/语义 key，避免 shadow/坐标后缀等退化 key），
      其余 key 的映射置 0（等同移除），让后续导入自动分配新的 guid，避免合并覆盖。
    """
    mapping = dict(ui_key_to_guid or {})
    guid_to_keys: Dict[int, List[str]] = {}
    for k, v in mapping.items():
        key = str(k or "").strip()
        if key == "":
            continue
        guid = int(v or 0)
        if guid <= 0:
            continue
        guid_to_keys.setdefault(guid, []).append(key)

    duplicates: List[Dict[str, Any]] = []
    removed_total = 0
    kept_total = 0

    for guid, keys in guid_to_keys.items():
        uniq = sorted(set(keys))
        if len(uniq) <= 1:
            continue

        # 保留“更稳定、语义更强”的 key（避免坐标后缀/装饰 shadow 抢占）
        keep_key = sorted(uniq, key=_ui_key_keep_preference_sort_key)[0]
        removed_keys = [k for k in uniq if k != keep_key]
        for rk in removed_keys:
            mapping[rk] = 0
            removed_total += 1
        kept_total += 1
        duplicates.append({"guid": int(guid), "kept_ui_key": keep_key, "removed_ui_keys": removed_keys})

    # 清理掉 value<=0 的条目（保持 registry 干净）
    cleaned = {k: int(v) for k, v in mapping.items() if str(k or "").strip() != "" and int(v or 0) > 0}

    return cleaned, {
        "duplicate_guid_groups_total": int(len(duplicates)),
        "dedup_removed_ui_keys_total": int(removed_total),
        "dedup_kept_guid_total": int(kept_total),
        "duplicates": duplicates[:100],
        "note": "当 registry 存在多个 ui_key 指向同一 guid 时，会保留更稳定/语义更强的 key（优先交互/语义 key），其余映射清空以强制后续导入重新分配 guid，避免覆盖/组合并。",
    }


def try_resolve_management_dir_from_template_json_path(template_json_path: Path) -> Optional[Path]:
    """
    尝试从模板 JSON 的位置推断项目存档的“管理配置”目录：
    - 约定：assets/资源库/项目存档/<package_id>/管理配置/UI源码/*.ui_bundle.json
    - 则 management_dir = .../<package_id>/管理配置
    """
    p = Path(template_json_path).resolve()
    parts = [str(x) for x in p.parts]
    try:
        idx = parts.index("管理配置")
    except ValueError:
        return None
    if idx <= 0:
        return None
    return Path(*p.parts[: idx + 1]).resolve()


def try_resolve_workspace_root_and_package_id_from_template_json_path(
    template_json_path: Path,
) -> Optional[Tuple[Path, str]]:
    """尽力从 template_json_path 推断 (workspace_root, package_id)。

    约定：
    - <workspace>/assets/资源库/项目存档/<package_id>/...
    """
    p = Path(template_json_path).resolve()
    parts = list(p.parts)
    assets_index: Optional[int] = None
    for i, part in enumerate(parts):
        if str(part) == "assets":
            assets_index = int(i)
            break
    if assets_index is None:
        return None
    project_index: Optional[int] = None
    for i, part in enumerate(parts):
        if str(part) == "项目存档":
            project_index = int(i)
            break
    if project_index is None or project_index + 1 >= len(parts):
        return None
    workspace_root = Path(*parts[:assets_index]).resolve()
    package_id = str(parts[project_index + 1]).strip()
    if not package_id:
        return None
    return workspace_root, package_id


def write_ui_click_actions_mapping_file(
    *,
    template_json_path: Path,
    click_actions: List[Dict[str, Any]],
) -> Optional[Path]:
    """
    将“可点击道具展示”的 GUID → action/args/ui_key 映射写入运行时缓存（不落资源库），供程序员写节点图时查阅/生成逻辑。
    """
    resolved = try_resolve_workspace_root_and_package_id_from_template_json_path(template_json_path)
    if resolved is None:
        return None
    workspace_root, package_id = resolved
    from engine.utils.cache.cache_paths import get_ui_actions_cache_dir

    out_dir = get_ui_actions_cache_dir(workspace_root, package_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = (out_dir / f"{Path(template_json_path).stem}.ui_actions.json").resolve()
    payload = {
        "version": 1,
        "source_ui_bundle_json": str(Path(template_json_path).resolve()),
        "click_actions": click_actions,
        "note": "本文件由 web_ui_import 写回链路自动生成：用于将 UI 点击事件的事件源GUID映射到 action_key/args（不绑定实现方式）。该文件属于运行时缓存（不落资源库）。",
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path

