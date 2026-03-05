from __future__ import annotations

"""
ui_guid_resolution.py

单一真源：基于 `.gil` dump-json 的 UI records（root4/9/502）反查并解析 `ui_key:` 占位符应回填的 GUID。

该模块只描述“规则与索引结构”，不负责 IO 与 pipeline 编排，供：
- 节点图写回（node_graph_writeback）
- 节点图导出（pipelines/project_export_gia）
- 诊断工具（commands/inspect_ui_guid）
共同复用，避免口径分叉。
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


def extract_ui_record_primary_guid(record: dict[str, object]) -> int | None:
    guid_candidates = record.get("501")
    if isinstance(guid_candidates, int):
        return int(guid_candidates)
    if not isinstance(guid_candidates, list):
        return None
    for g0 in guid_candidates:
        if isinstance(g0, int):
            return int(g0)
    return None


def extract_ui_record_primary_name(record: dict[str, object]) -> str | None:
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return None
    for component in component_list:
        if not isinstance(component, dict):
            continue
        name_container = component.get("12")
        if not isinstance(name_container, dict):
            continue
        name_text = name_container.get("501")
        if isinstance(name_text, str) and name_text != "":
            return name_text
    return None


def extract_ui_record_component_type_ids(record: dict[str, object]) -> set[int]:
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return set()
    out: set[int] = set()
    for component in component_list:
        if not isinstance(component, dict):
            continue
        type_id = component.get("502")
        if isinstance(type_id, int):
            out.add(int(type_id))
    return out


@dataclass(slots=True)
class UiRecordIndex:
    guid_set: set[int]
    name_by_guid: dict[int, str]
    parent_by_guid: dict[int, int | None]
    children_by_parent: dict[int, list[int]]
    component_type_ids_by_guid: dict[int, set[int]]
    guids_by_name: dict[str, list[int]]


def build_ui_record_index_from_record_list(record_list: list[object]) -> UiRecordIndex | None:
    guid_set: set[int] = set()
    name_by_guid: dict[int, str] = {}
    parent_by_guid: dict[int, int | None] = {}
    children_by_parent: dict[int, list[int]] = {}
    component_type_ids_by_guid: dict[int, set[int]] = {}
    guids_by_name: dict[str, list[int]] = {}

    for r0 in record_list:
        if not isinstance(r0, dict):
            continue

        primary_guid = extract_ui_record_primary_guid(r0)
        if primary_guid is not None and int(primary_guid) > 0:
            parent_value = r0.get("504")
            parent_guid = int(parent_value) if isinstance(parent_value, int) else None
            parent_by_guid[int(primary_guid)] = parent_guid
            if parent_guid is not None:
                children_by_parent.setdefault(int(parent_guid), []).append(int(primary_guid))

            nm = extract_ui_record_primary_name(r0)
            if isinstance(nm, str) and nm != "":
                name_by_guid[int(primary_guid)] = str(nm)
                guids_by_name.setdefault(str(nm), []).append(int(primary_guid))

            component_type_ids_by_guid[int(primary_guid)] = extract_ui_record_component_type_ids(r0)

        guid_candidates = r0.get("501")
        if isinstance(guid_candidates, int) and int(guid_candidates) > 0:
            guid_set.add(int(guid_candidates))
        elif isinstance(guid_candidates, list):
            for g0 in guid_candidates:
                if isinstance(g0, int) and int(g0) > 0:
                    guid_set.add(int(g0))

    if not guid_set:
        return None

    return UiRecordIndex(
        guid_set=set(guid_set),
        name_by_guid=dict(name_by_guid),
        parent_by_guid=dict(parent_by_guid),
        children_by_parent={k: sorted(v) for k, v in children_by_parent.items()},
        component_type_ids_by_guid=dict(component_type_ids_by_guid),
        guids_by_name={k: sorted(v) for k, v in guids_by_name.items()},
    )


def infer_root_layout_name_for_guid(
    *,
    guid: int,
    parent_by_guid: dict[int, int | None],
    name_by_guid: dict[int, str],
    cache: dict[int, str | None],
) -> str | None:
    if int(guid) in cache:
        return cache[int(guid)]

    cur = int(guid)
    visited: set[int] = set()
    while True:
        if cur in visited:
            cache[int(guid)] = None
            return None
        visited.add(cur)
        parent = parent_by_guid.get(cur)
        if parent is None:
            root_name = name_by_guid.get(cur)
            cache[int(guid)] = str(root_name) if isinstance(root_name, str) and root_name != "" else None
            return cache[int(guid)]
        cur = int(parent)


def resolve_ui_key_guid_from_output_gil(
    *,
    ui_key: str,
    layout_name_hint: str | None,
    ui_index: UiRecordIndex,
    root_name_cache: dict[int, str | None],
) -> int | None:
    """
    以 output_gil 的 UI records 为准，反查某个 ui_key 占位符应回填的 GUID。

    解决的问题：
    - Graph Code 仍使用旧口径（例如 `HTML导入_界面布局__btn_back__btn_item`），但 registry 已升级为“带页面前缀/状态”的新口径；
    - 同名控件（如 btn_exit）在不同页面会出现多份，必须用 layout 根节点名做消歧；
    - 部分按钮以 decor 方式导出：没有独立的 `btn_item` 子控件，此时回填为组容器 guid（组本身带交互组件）。
    """
    key = str(ui_key or "").strip()
    if key == "":
        return None

    def _filter_by_layout(guids: list[int]) -> list[int]:
        if not guids:
            return []
        if layout_name_hint is None or str(layout_name_hint).strip() == "":
            return list(guids)
        want = str(layout_name_hint).strip()
        out: list[int] = []
        for g in guids:
            root_name = infer_root_layout_name_for_guid(
                guid=int(g),
                parent_by_guid=ui_index.parent_by_guid,
                name_by_guid=ui_index.name_by_guid,
                cache=root_name_cache,
            )
            if root_name == want:
                out.append(int(g))
        return out

    def _pick_single(guids: list[int]) -> int | None:
        uniq = sorted({int(g) for g in guids if int(g) > 0})
        if len(uniq) == 1:
            return int(uniq[0])
        return None

    # stable alias：UI_STATE_GROUP__<group>__<state>__group
    if key.startswith("UI_STATE_GROUP__"):
        parts = [p for p in key.split("__") if str(p)]
        if len(parts) >= 4 and parts[0] == "UI_STATE_GROUP" and parts[-1] == "group":
            group = str(parts[1]).strip()
            state = str(parts[2]).strip()
            candidates_group: list[str] = [group]
            if group.endswith("_state"):
                candidates_group.append(group[: -len("_state")])
            else:
                candidates_group.append(group + "_state")

            for gname in candidates_group:
                if gname == "" or state == "":
                    continue
                record_name = f"组件组_{gname}__{state}"
                guids = _filter_by_layout(ui_index.guids_by_name.get(record_name, []))
                picked = _pick_single(guids)
                if picked is not None:
                    return int(picked)
        return None

    # general: <prefix>__<data-ui-key>__<suffix...>
    parts = [p for p in key.split("__") if str(p)]
    if len(parts) < 3:
        return None

    data_ui_key = str(parts[1]).strip()
    suffix_parts = [str(p).strip() for p in parts[2:] if str(p).strip() != ""]
    if data_ui_key == "" or not suffix_parts:
        return None

    tail_last = suffix_parts[-1]

    def _find_group_guid(group_suffix: str) -> int | None:
        record_name = f"组件组_{group_suffix}"
        guids = _filter_by_layout(ui_index.guids_by_name.get(record_name, []))
        return _pick_single(guids)

    def _find_btn_item_under_group(group_guid: int) -> int | None:
        children = list(ui_index.children_by_parent.get(int(group_guid), []))
        candidates: list[int] = []
        for child_guid in children:
            name = ui_index.name_by_guid.get(int(child_guid))
            type_ids = ui_index.component_type_ids_by_guid.get(int(child_guid), set())
            if 35 in type_ids:
                candidates.append(int(child_guid))
                continue
            if isinstance(name, str) and name.startswith("按钮_道具展示"):
                candidates.append(int(child_guid))
        uniq = sorted({int(x) for x in candidates if int(x) > 0})
        if len(uniq) == 1:
            return int(uniq[0])
        if len(uniq) > 1:
            return int(uniq[0])
        return None

    # group
    if tail_last == "group":
        state_parts = suffix_parts[:-1]
        group_suffix = data_ui_key if not state_parts else f"{data_ui_key}__{'__'.join(state_parts)}"
        return _find_group_guid(group_suffix)

    # btn_item
    if tail_last == "btn_item":
        state_parts = suffix_parts[:-1]

        # 1) explicit state: <data_ui_key>__<state...>
        if state_parts:
            group_suffix = f"{data_ui_key}__{'__'.join(state_parts)}"
            group_guid = _find_group_guid(group_suffix)
            if group_guid is None:
                return None
            btn_item_guid = _find_btn_item_under_group(int(group_guid))
            return int(btn_item_guid) if btn_item_guid is not None else int(group_guid)

        # 2) no state: try direct group first
        group_guid = _find_group_guid(data_ui_key)
        if group_guid is not None:
            btn_item_guid = _find_btn_item_under_group(int(group_guid))
            return int(btn_item_guid) if btn_item_guid is not None else int(group_guid)

        # 3) fallback: try group name variants (btn_allow -> btn_allow_state)
        group_guid2 = _find_group_guid(data_ui_key + "_state")
        if group_guid2 is not None:
            btn_item_guid2 = _find_btn_item_under_group(int(group_guid2))
            return int(btn_item_guid2) if btn_item_guid2 is not None else int(group_guid2)

        # 4) fallback: scan stateful groups under this layout, pick one that contains item_display
        want_root = str(layout_name_hint or "").strip()
        prefix_variants = [f"组件组_{data_ui_key}__", f"组件组_{data_ui_key}_state__"]
        prefer_state_prefixes = ["unselected", "enabled", "normal"]
        best_rank: tuple[int, int] | None = None  # (state_rank, guid)
        best_btn_item: int | None = None

        for record_name, guids in ui_index.guids_by_name.items():
            if not isinstance(record_name, str) or not record_name.startswith("组件组_"):
                continue
            if want_root != "":
                # 快路径：若该 name 下的任一 guid 不在目标 layout，则跳过（避免跨页面误选）
                guids2 = _filter_by_layout(list(guids))
                if not guids2:
                    continue
            else:
                guids2 = list(guids)

            if not any(record_name.startswith(pfx) for pfx in prefix_variants):
                continue

            # 组件组_<data_ui_key>__<state...>
            state_text = record_name.split("组件组_", 1)[1]
            if state_text.startswith(data_ui_key + "__"):
                state_text = state_text[len(data_ui_key + "__") :]
            elif state_text.startswith(data_ui_key + "_state__"):
                state_text = state_text[len(data_ui_key + "_state__") :]
            else:
                continue
            state_label = state_text.split("__", 1)[0].strip()
            state_rank = prefer_state_prefixes.index(state_label) if state_label in prefer_state_prefixes else 99

            picked_group = _pick_single(_filter_by_layout(list(guids2)))
            if picked_group is None:
                continue

            btn_item_guid3 = _find_btn_item_under_group(int(picked_group))
            if btn_item_guid3 is None:
                btn_item_guid3 = int(picked_group)

            rank = (int(state_rank), int(btn_item_guid3))
            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_btn_item = int(btn_item_guid3)

        return int(best_btn_item) if best_btn_item is not None else None

    return None


def apply_legacy_ui_key_aliases_for_required_keys(
    *,
    ui_key_to_guid_registry: Mapping[str, int],
    required_ui_keys: Iterable[str],
) -> Dict[str, int]:
    """
    旧 UIKey 别名兜底（纯规则，无 IO）：

    背景：UI 写回可能对 registry 做“按 GUID 去重”（injective），保留更具体/更长的 key；
    导致历史节点图仍在使用的“短别名”被移除，例如：
    - HTML导入_界面布局__btn_allow__btn_item   （旧）
    - HTML导入_界面布局__btn_allow__enabled__btn_item（新，保留）

    策略（保守）：
    - 仅当 required_ui_keys 中出现缺失 key，且 registry 中存在可推导的更长 key 时，回填别名；
    - 该回填是否落盘由上层 pipeline 决定（本函数不写盘）。
    """
    updated: Dict[str, int] = {str(k): int(v) for k, v in dict(ui_key_to_guid_registry or {}).items() if isinstance(v, int)}

    # 状态优先级：按钮/组容器默认取 enabled/show（更贴近“可交互默认态”）
    preferred_states_btn = ["enabled", "show", "open", "on", "normal", "default", "active", "selected"]
    preferred_states_misc = ["show", "enabled", "normal", "default", "active"]

    def _try_pick_by_state_and_suffix(*, prefix: str, data_ui_key: str, suffix: str, preferred_states: Sequence[str]) -> int | None:
        # 1) <prefix>__<data>__<state>__<suffix>
        for st in list(preferred_states):
            cand = f"{prefix}__{data_ui_key}__{st}__{suffix}"
            guid = updated.get(cand)
            if isinstance(guid, int) and int(guid) > 0:
                return int(guid)

        # 2) any <prefix>__<data>__*__<suffix>
        prefix2 = f"{prefix}__{data_ui_key}__"
        tail = f"__{suffix}"
        candidates = [k for k in updated.keys() if str(k).startswith(prefix2) and str(k).endswith(tail)]
        if candidates:

            def _score(k: str) -> Tuple[int, int, str]:
                # prefer enabled/show... ; then more specific ; then stable
                k2 = str(k)
                state_rank = 999
                for i, st in enumerate(list(preferred_states)):
                    if f"__{st}__" in k2:
                        state_rank = i
                        break
                return (state_rank, -len(k2), k2)

            chosen = sorted({str(x) for x in candidates}, key=_score)[0]
            guid2 = updated.get(chosen)
            if isinstance(guid2, int) and int(guid2) > 0:
                return int(guid2)

        # 3) exact <prefix>__<data>__<suffix>
        guid3 = updated.get(f"{prefix}__{data_ui_key}__{suffix}")
        if isinstance(guid3, int) and int(guid3) > 0:
            return int(guid3)
        return None

    required = sorted({str(k or "").strip() for k in list(required_ui_keys or []) if str(k or "").strip()})
    for key in required:
        existing = updated.get(str(key))
        if isinstance(existing, int) and int(existing) > 0:
            continue

        parts = [p for p in str(key).split("__") if str(p)]

        # ---- 4-part legacy key: <layout_prefix>__<state_group>__<state>__<suffix>
        # 常见于历史节点图：HTML导入_界面布局__tutorial_overlay__guide_0__btn_item
        # 现代 registry 更稳定的口径：UI_STATE_GROUP__<state_group>__<state>__group
        if len(parts) == 4:
            prefix, state_group, state_name, suffix = (str(parts[0]), str(parts[1]), str(parts[2]), str(parts[3]))
            if prefix and state_group and state_name and suffix in {"btn_item", "group"}:
                if state_group.endswith("_state"):
                    group_name_candidates = [state_group, state_group[: -len("_state")]]
                else:
                    group_name_candidates = [state_group, f"{state_group}_state"]

                state_candidates = [state_name]
                if state_name in {"done", "finish", "finished", "end", "ended", "complete", "completed"}:
                    state_candidates += ["hidden", "show"]
                else:
                    state_candidates += ["enabled", "show", "hidden"]

                resolved: int | None = None
                for gname in group_name_candidates:
                    for st in state_candidates:
                        cand = f"UI_STATE_GROUP__{gname}__{st}__group"
                        guid = updated.get(cand)
                        if isinstance(guid, int) and int(guid) > 0:
                            resolved = int(guid)
                            break
                    if resolved is not None:
                        break

                # 最后兜底：该 state_group 任意已有的状态（优先 enabled/show/hidden）
                if resolved is None:
                    for gname in group_name_candidates:
                        prefix2 = f"UI_STATE_GROUP__{gname}__"
                        suffix2 = "__group"
                        candidates2 = [k for k in updated.keys() if str(k).startswith(prefix2) and str(k).endswith(suffix2)]
                        if not candidates2:
                            continue

                        def _score_state_key(k: str) -> Tuple[int, str]:
                            kk = str(k)
                            rank = 999
                            if "__enabled__" in kk:
                                rank = 0
                            elif "__show__" in kk:
                                rank = 1
                            elif "__hidden__" in kk:
                                rank = 2
                            return (rank, kk)

                        chosen2 = sorted({str(x) for x in candidates2}, key=_score_state_key)[0]
                        guid2 = updated.get(chosen2)
                        if isinstance(guid2, int) and int(guid2) > 0:
                            resolved = int(guid2)
                            break

                if resolved is not None and int(resolved) > 0:
                    updated[str(key)] = int(resolved)
            continue

        if len(parts) != 3:
            continue
        prefix, data_ui_key, suffix = (str(parts[0]), str(parts[1]), str(parts[2]))
        if prefix == "" or data_ui_key == "" or suffix == "":
            continue

        # 仅对“稳定后缀”做别名回填：避免误伤其它 key 形态
        if suffix not in {"btn_item", "group", "rect", "text", "shadow", "btn_fill", "rect_shadow"}:
            continue

        preferred_states = preferred_states_btn if suffix in {"btn_item", "group"} else preferred_states_misc
        resolved_guid = _try_pick_by_state_and_suffix(
            prefix=prefix,
            data_ui_key=data_ui_key,
            suffix=suffix,
            preferred_states=preferred_states,
        )

        # 关键兜底：某些“可点击按钮”导出为 decor 形态，没有独立 btn_item 子控件；
        # 此时节点图用 *__btn_item 引用时，回退到同组容器 guid。
        if resolved_guid is None and suffix == "btn_item":
            resolved_guid = _try_pick_by_state_and_suffix(
                prefix=prefix,
                data_ui_key=data_ui_key,
                suffix="group",
                preferred_states=preferred_states_btn,
            )

        if resolved_guid is not None and int(resolved_guid) > 0:
            updated[str(key)] = int(resolved_guid)

    return updated


def infer_ui_key_guid_registry_overrides_from_ui_records_for_group_and_btn_item(
    *,
    ui_key_to_guid_registry: Mapping[str, int],
    ui_records: list[object],
) -> Dict[str, int]:
    """
    工程化修复（纯规则，无 IO）：
    当 registry 与 `.gil` 的 UI records 不一致时，尝试“按命名约定”推断应覆盖的 GUID。

    约束（保守）：
    - 仅对 suffix 为 `__group` / `__btn_item` 的 key 尝试修正。
    - `__group`：按 UI record 名称精确匹配 `组件组_<data-ui-key>` 定位 group guid。
    - `__btn_item`：先找到 group guid，再在其子项中挑选“道具展示按钮”（component type_id == 15）guid。
    """
    registry = {str(k): int(v) for k, v in dict(ui_key_to_guid_registry or {}).items() if isinstance(v, int)}
    ui_index = build_ui_record_index_from_record_list(list(ui_records))
    if ui_index is None:
        return {}

    group_name_to_guid: Dict[str, int] = {}
    guid_to_parent: Dict[int, int | None] = dict(ui_index.parent_by_guid)
    guid_to_name: Dict[int, str] = dict(ui_index.name_by_guid)
    guid_to_component_type_ids: Dict[int, set[int]] = dict(ui_index.component_type_ids_by_guid)

    for guid, name in guid_to_name.items():
        if str(name).startswith("组件组_"):
            group_name_to_guid[str(name)] = int(guid)

    def infer_group_guid_for_data_ui_key(data_ui_key: str) -> int | None:
        key = str(data_ui_key or "").strip()
        if key == "":
            return None
        return group_name_to_guid.get(f"组件组_{key}")

    def infer_btn_item_guid_for_group(group_guid: int) -> int | None:
        candidates: list[int] = []
        candidates_by_name: list[int] = []
        for guid, parent in guid_to_parent.items():
            if parent is None or int(parent) != int(group_guid):
                continue
            type_ids = guid_to_component_type_ids.get(int(guid), set())
            if 15 not in type_ids:
                continue
            candidates.append(int(guid))
            nm = guid_to_name.get(int(guid))
            if isinstance(nm, str) and nm.startswith("按钮_道具展示_"):
                candidates_by_name.append(int(guid))

        if len(candidates_by_name) == 1:
            return int(candidates_by_name[0])
        if len(candidates) == 1:
            return int(candidates[0])
        return None

    overrides: Dict[str, int] = {}
    for ui_key, old_guid in list(registry.items()):
        key_text = str(ui_key or "").strip()
        if key_text == "" or "__" not in key_text:
            continue
        parts = [p for p in key_text.split("__") if str(p)]
        if len(parts) < 2:
            continue
        data_ui_key = str(parts[1]).strip()
        if data_ui_key == "":
            continue
        suffix = str(parts[-1]).strip()

        if suffix == "group":
            inferred = infer_group_guid_for_data_ui_key(data_ui_key)
            if inferred is None:
                continue
            if int(inferred) != int(old_guid):
                overrides[key_text] = int(inferred)
            continue

        if suffix == "btn_item":
            group_guid = infer_group_guid_for_data_ui_key(data_ui_key)
            if group_guid is None:
                continue
            inferred_btn = infer_btn_item_guid_for_group(int(group_guid))
            if inferred_btn is None:
                continue
            if int(inferred_btn) != int(old_guid):
                overrides[key_text] = int(inferred_btn)
            continue

    return overrides


def fill_missing_required_ui_keys_from_ui_records(
    *,
    ui_key_to_guid_registry: Mapping[str, int],
    required_ui_keys: Iterable[str],
    ui_records: list[object],
    layout_name_hint: str | None,
) -> tuple[Dict[str, int], List[Dict[str, object]]]:
    """
    工程化兜底（纯规则，无 IO）：当 registry 缺失某些 required_ui_keys 时，
    尝试从 UI records 反查 GUID 并补齐；返回 (updated_registry, changes_report)。
    """
    updated: Dict[str, int] = {str(k): int(v) for k, v in dict(ui_key_to_guid_registry or {}).items() if isinstance(v, int)}
    ui_index = build_ui_record_index_from_record_list(list(ui_records))
    if ui_index is None:
        return updated, []

    root_name_cache: dict[int, str | None] = {}
    changes: List[Dict[str, object]] = []
    required = sorted({str(k or "").strip() for k in list(required_ui_keys or []) if str(k or "").strip()})
    for key in required:
        existing = updated.get(str(key))
        if isinstance(existing, int) and int(existing) > 0:
            continue
        inferred = resolve_ui_key_guid_from_output_gil(
            ui_key=str(key),
            layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
            ui_index=ui_index,
            root_name_cache=root_name_cache,
        )
        if inferred is None or int(inferred) <= 0:
            continue
        updated[str(key)] = int(inferred)
        changes.append({"ui_key": str(key), "new_guid": int(inferred), "kind": "filled_from_base_ui_records"})

    return updated, changes


