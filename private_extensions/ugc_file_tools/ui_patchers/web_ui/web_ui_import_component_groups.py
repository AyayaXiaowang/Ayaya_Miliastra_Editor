from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    allocate_next_guid as _allocate_next_guid,
    find_record_by_guid as _find_record_by_guid,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    set_widget_parent_guid_field504 as _set_widget_parent_guid_field504,
)
from .web_ui_import_context import WebUiImportContext
from .web_ui_import_grouping import (
    build_group_container_record_from_prototype,
    ensure_child_in_parent_children,
    ensure_list_min_len,
    get_atomic_component_group_key,
    is_group_container_record_shape,
    strip_ui_key_prefix_for_group_name,
)
from .web_ui_import_visibility import apply_visibility_patch
from .web_ui_import_rect import try_extract_widget_name


def _derive_group_container_display_name(
    group_key: str,
    *,
    state_group_name: str = "",
    state_name: str = "",
) -> str:
    """
    组容器在编辑器层级里的显示名称（避免“不同状态组同名”）。

    多状态组件（UI state group）优先用 `state_group + state` 命名，避免出现大量 `组件组_ready / 组件组_wait / ...`
    这类同名并列导致的“层级看起来错乱”。

    约定（以 `ceshi.html` 关卡按钮为例）：
    - group_key: <layout>__level_unselected__level_01
    - group_key: <layout>__level_selected__level_01
    - group_key: <layout>__level_cleared_mark__level_01
    若仅取末尾 token（level_01），会导致三者同名，层级面板极其难用。
    """
    # 1) UI 多状态组：优先用 state_group/state（来自 Workbench 导出元信息），确保同一页内可读且唯一
    state_group = str(state_group_name or "").strip()
    state = str(state_name or "").strip()
    if state_group != "" and state != "":
        return f"组件组_{state_group}__{state}"
    if state_group != "":
        return f"组件组_{state_group}"

    parts = [p for p in str(group_key or "").split("__") if p != ""]
    if not parts:
        return "组件组"

    # 针对关卡按钮状态组：用“状态 + 关卡号”区分
    if len(parts) >= 3:
        state_token = str(parts[-2])
        id_token = str(parts[-1])
        if id_token.startswith("level_") and state_token in {"level_unselected", "level_selected", "level_cleared_mark"}:
            state_name = {
                "level_unselected": "未选",
                "level_selected": "已选",
                "level_cleared_mark": "通关标记",
            }[state_token]
            return f"组件组_{state_name}_{id_token}"

    readable = strip_ui_key_prefix_for_group_name(str(group_key or ""))
    if readable:
        return f"组件组_{readable}"
    return "组件组"


@dataclass(slots=True)
class ComponentGroupsState:
    group_records: Dict[str, Dict[str, Any]]
    group_guids: Dict[str, int]
    group_child_guids: Dict[str, List[int]]
    group_child_entries: Dict[str, List[Tuple[int, int, int]]]
    ordered_group_keys: List[str]
    group_guid_collision_avoided: List[Dict[str, Any]]
    reserved_group_guid_to_ui_key: Dict[int, str]


def build_component_group_containers(ctx: WebUiImportContext, *, widgets: List[Any]) -> ComponentGroupsState:
    # ------------------------------------------------------------------ 组件打组（Web 扁平层 -> GIL 层级）
    # 目标：同一 HTML 元素导出的多个扁平控件（背景/边框/阴影/文字...）在写回 `.gil` 时挂到同一个“组容器”下，
    # 便于在编辑器层级中整体控制。
    #
    # 简单策略（回退）：不做自动拆层；每个组件/状态就是一个组。
    group_members: Dict[str, List[Dict[str, Any]]] = {}
    ordered_group_keys: List[str] = []

    for w in widgets:
        if not isinstance(w, dict):
            continue
        gk = get_atomic_component_group_key(w)
        if gk == "":
            continue
        if gk not in group_members:
            group_members[gk] = []
            ordered_group_keys.append(gk)
        group_members[gk].append(w)

    # 组容器创建策略：
    # - 常规组件：仅当同组成员>=2 时创建组容器（避免层级膨胀）。
    # - UI 多状态组件（带 __ui_state_group）：即使同组成员==1 也创建组容器，便于节点图一键切换。
    group_records: Dict[str, Dict[str, Any]] = {}
    group_guids: Dict[str, int] = {}
    group_child_guids: Dict[str, List[int]] = {}
    group_child_entries: Dict[str, List[Tuple[int, int, int]]] = {}
    group_guid_collision_avoided: List[Dict[str, Any]] = []
    reserved_group_guid_to_ui_key: Dict[int, str] = {}

    # 注意：组容器 record 必须是“纯组容器”（component_list 只有 2 个，不包含 RectTransform），
    # 不能 clone 任意控件 record（否则会把进度条/文本框的组件列表塞进组容器，表现为“组里出现进度条样式”）。
    seen_state_groups: set[str] = set()
    for gk in ordered_group_keys:
        members = group_members.get(gk) or []
        is_ui_state_group = any(bool(str(m.get("__ui_state_group") or "").strip()) for m in members if isinstance(m, dict))
        # 额外规则：若任一成员显式声明“需要沉淀为自定义模板”，即使组内只有 1 个控件也创建组容器。
        # 目的：让“单控件模板沉淀”也拥有稳定的 group_guid，可在导出阶段保存到控件组库。
        has_custom_template_mark = any(
            bool(str((m.get("__ui_custom_template_name") or "")).strip()) for m in members if isinstance(m, dict)
        )
        should_create_group_container = (len(members) >= 2) or bool(is_ui_state_group) or bool(has_custom_template_mark)
        if not should_create_group_container:
            continue

        desired_parent_guid = int(ctx.layout_guid)
        desired_parent_record = ctx.layout_record
        group_ui_key = f"{gk}__group"
        # 若这是“多状态组件组”，额外注册一个稳定别名：
        #   UI_STATE_GROUP__<state_group>__<state>__group -> <group_guid>
        # 目的：节点图/脚本侧不必依赖 gk 的具体拼接规则（可能受 ui_key/去重后缀影响），只依赖“状态组名 + 状态名”。
        state_group_name = ""
        state_name = ""
        if is_ui_state_group:
            state_groups = {
                str(m.get("__ui_state_group") or "").strip()
                for m in members
                if isinstance(m, dict) and str(m.get("__ui_state_group") or "").strip() != ""
            }
            states = {
                str(m.get("__ui_state") or "").strip()
                for m in members
                if isinstance(m, dict) and str(m.get("__ui_state") or "").strip() != ""
            }
            if len(state_groups) == 1:
                state_group_name = sorted(state_groups)[0]
            if len(states) == 1:
                state_name = sorted(states)[0]
            if state_group_name:
                seen_state_groups.add(str(state_group_name))

        group_name = _derive_group_container_display_name(
            gk,
            state_group_name=state_group_name,
            state_name=state_name,
        )
        # 注意：即便 registry 本轮是“首次创建”（ctx.registry_loaded=False），也应该允许写入新的 UIKey→GUID 映射。
        # registry_loaded 仅代表“是否从磁盘加载了旧映射”，不应影响“本轮是否产出映射表”。
        desired_group_guid = int(ctx.ui_key_to_guid.get(group_ui_key) or 0)
        existing_group_record: Optional[Dict[str, Any]] = None
        if desired_group_guid > 0:
            prev_group_key = reserved_group_guid_to_ui_key.get(int(desired_group_guid))
            if prev_group_key is not None and prev_group_key != group_ui_key:
                # 关键护栏：同一次写回中，两个不同 group_ui_key 绝不允许复用同一个 group guid。
                group_guid_collision_avoided.append(
                    {
                        "ui_key": group_ui_key,
                        "expected_widget_type": "组容器",
                        "desired_guid": int(desired_group_guid),
                        "existing_widget_name": "",
                        "reason": f"group_guid_already_reserved_by_other_group_ui_key:{prev_group_key}",
                    }
                )
                desired_group_guid = 0

        if desired_group_guid > 0:
            existing_group_record = _find_record_by_guid(ctx.ui_record_list, int(desired_group_guid))
            if existing_group_record is not None:
                parent_children_now = _get_children_guids_from_parent_record(desired_parent_record)
                if int(desired_group_guid) not in parent_children_now:
                    group_guid_collision_avoided.append(
                        {
                            "ui_key": group_ui_key,
                            "expected_widget_type": "组容器",
                            "desired_guid": int(desired_group_guid),
                            "existing_widget_name": (try_extract_widget_name(existing_group_record) or ""),
                            "reason": "guid_exists_but_not_in_expected_parent_children",
                        }
                    )
                    existing_group_record = None
            if existing_group_record is not None and not is_group_container_record_shape(existing_group_record):
                group_guid_collision_avoided.append(
                    {
                        "ui_key": group_ui_key,
                        "expected_widget_type": "组容器",
                        "desired_guid": int(desired_group_guid),
                        "existing_widget_name": (try_extract_widget_name(existing_group_record) or ""),
                        "reason": "guid_record_shape_mismatch_not_a_group_container",
                    }
                )
                existing_group_record = None

        group_record: Dict[str, Any]
        group_guid: int
        created_new_group_record = False
        if existing_group_record is not None:
            group_record = existing_group_record
            group_guid = int(desired_group_guid)
            _set_widget_parent_guid_field504(group_record, int(desired_parent_guid))
        else:
            group_guid = _allocate_next_guid(ctx.existing_guids, start=max(ctx.existing_guids) + 1)
            ctx.existing_guids.add(int(group_guid))
            # 本轮创建的新组容器必须写入映射表（无论 registry 是否预先存在），
            # 否则会导致“UI+节点图同次写回”时节点图无法解析 ui_key:UI_STATE_GROUP__... 占位符。
            ctx.ui_key_to_guid[group_ui_key] = int(group_guid)
            group_record = build_group_container_record_from_prototype(
                prototype_record=ctx.group_container_prototype_record,
                group_guid=int(group_guid),
                parent_guid=int(desired_parent_guid),
                group_name=str(group_name),
            )
            created_new_group_record = True

        # 关键：复用已有组容器 record 时也必须写回 group_ui_key→guid，
        # 否则当旧 registry 缺该 key 时，本轮写回不会补齐，节点图侧引用会失败。
        ctx.ui_key_to_guid[str(group_ui_key)] = int(group_guid)

        if state_group_name != "" and state_name != "":
            ctx.ui_key_to_guid[f"UI_STATE_GROUP__{state_group_name}__{state_name}__group"] = int(group_guid)

        # 基底兼容（关键）：当 ctx 提供 group_container_prototype_record 时，组容器已由 prototype clone，
        # 不能再强制覆盖为固定样本形态，否则会把“基底组容器专属 meta 结构”抹掉，导致编辑器打不开。
        if ctx.group_container_prototype_record is None:
            # 兼容：部分基底 record 的 meta/component 列表长度不足；先补齐占位，再强制写成“组容器”样本形态。
            ensure_list_min_len(group_record, "502", 2)
            ensure_list_min_len(group_record, "505", 2)
            from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import force_record_to_group_container_shape as _force_group

            _force_group(group_record)
        else:
            if not is_group_container_record_shape(group_record):
                raise RuntimeError("group container record shape mismatch after prototype clone")

        # name（统一在完成“组容器形态校验/补齐”之后再写入）
        from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import set_widget_name as _set_name2

        _set_name2(group_record, group_name)

        if created_new_group_record:
            ctx.ui_record_list.append(group_record)
        ensure_child_in_parent_children(desired_parent_record, int(group_guid))

        # UI 多状态：用“组容器可见性”表达默认态，其它态初始隐藏；
        # 同时将子控件 initial_visible 强制为 True，确保节点图只切组容器即可显示整组内容。
        desired_group_visible: Optional[bool] = None
        if is_ui_state_group:
            desired_group_visible = any(bool(m.get("initial_visible", True)) for m in members if isinstance(m, dict))
            for m in members:
                if not isinstance(m, dict):
                    continue
                m["initial_visible"] = True
        else:
            # 非状态组：组容器本身必须默认可见。
            #
            # 背景：组容器 record 可能来自 base `.gil` 的 prototype clone，不同基底的“组容器默认可见性”并不一致；
            # 若不显式写回为可见，会出现“按钮/面板本身没有多状态，但整组被默认隐藏”的严重问题。
            desired_group_visible = True
        if desired_group_visible is not None:
            apply_visibility_patch(group_record, visible=bool(desired_group_visible))

        group_records[gk] = group_record
        group_guids[gk] = int(group_guid)
        group_child_guids[gk] = []
        group_child_entries[gk] = []
        reserved_group_guid_to_ui_key[int(group_guid)] = str(group_ui_key)
        # 让 widget 导入阶段也感知 group guid 占用，避免 registry 内出现“某 widget ui_key 复用 group guid”的极端情况。
        ctx.reserved_guid_to_ui_key.setdefault(int(group_guid), str(group_ui_key))

    # ------------------------------------------------------------------ hidden alias 清理（hidden 作为可选语义，不再强制单独 hidden GUID）
    #
    # 语义约定：
    # - “隐藏”本质是对目标组做关闭，不要求必须存在独立 hidden 组容器；
    # - 因此这里不再自动创建/复用 hidden 组容器映射，只在检测到“脏旧映射”时清理。
    #
    # 兼容性：
    # - 若 registry 中已有合法 hidden 映射，则保持不动（不主动破坏历史存量）；
    # - 若映射指向非法记录（非组容器/父级不符/被其它 key 占用），则移除，避免误绑到错误控件。
    if seen_state_groups:
        for sg in sorted({str(x).strip() for x in seen_state_groups if str(x).strip()}):
            hidden_key = f"UI_STATE_GROUP__{sg}__hidden__group"
            desired_parent_guid = int(ctx.layout_guid)
            mapped_hidden_guid = int(ctx.ui_key_to_guid.get(hidden_key) or 0)
            if mapped_hidden_guid <= 0:
                continue
            mapped_record = _find_record_by_guid(ctx.ui_record_list, int(mapped_hidden_guid))
            mapped_parent = mapped_record.get("504") if isinstance(mapped_record, dict) else None
            reserved_by = ctx.reserved_guid_to_ui_key.get(int(mapped_hidden_guid))
            mapping_is_valid = (
                isinstance(mapped_record, dict)
                and is_group_container_record_shape(mapped_record)
                and isinstance(mapped_parent, int)
                and int(mapped_parent) == int(desired_parent_guid)
                and (reserved_by is None or str(reserved_by) == str(hidden_key))
            )
            if bool(mapping_is_valid):
                continue
            ctx.guid_collision_avoided.append(
                {
                    "ui_key": str(hidden_key),
                    "expected_widget_type": "组容器",
                    "desired_guid": int(mapped_hidden_guid),
                    "existing_widget_name": (try_extract_widget_name(mapped_record) or "")
                    if isinstance(mapped_record, dict)
                    else "",
                    "reason": "stale_hidden_alias_mapping_removed",
                }
            )
            ctx.ui_key_to_guid.pop(hidden_key, None)

    return ComponentGroupsState(
        group_records=group_records,
        group_guids=group_guids,
        group_child_guids=group_child_guids,
        group_child_entries=group_child_entries,
        ordered_group_keys=ordered_group_keys,
        group_guid_collision_avoided=group_guid_collision_avoided,
        reserved_group_guid_to_ui_key=reserved_group_guid_to_ui_key,
    )

