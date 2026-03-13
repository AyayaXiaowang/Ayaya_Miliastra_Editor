from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

UI_COMPONENT_TYPE_ID_BUTTON = 35


def _extract_ui_record_primary_guid(record: dict[str, object]) -> int | None:
    """Extract primary guid from a UI record."""
    guid_candidates = record.get("501")
    if isinstance(guid_candidates, int):
        return int(guid_candidates)
    if not isinstance(guid_candidates, list):
        return None
    for g0 in guid_candidates:
        if isinstance(g0, int):
            return int(g0)
    return None


def _extract_ui_record_primary_name(record: dict[str, object]) -> str | None:
    """Extract primary name from a UI record."""
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
            return str(name_text)
    return None


def _ui_record_has_button_component(record: dict[str, object]) -> bool:
    """Return whether the UI record contains a button component."""
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return False
    for component in component_list:
        if not isinstance(component, dict):
            continue
        type_id = component.get("502")
        if isinstance(type_id, int) and int(type_id) == int(UI_COMPONENT_TYPE_ID_BUTTON):
            return True
    return False


@dataclass(slots=True)
class BackfillUiRecordIndex:
    """A minimized UI record index for export-center backfill identification."""

    name_by_guid: dict[int, str]
    parent_by_guid: dict[int, int | None]
    children_by_parent: dict[int, list[int]]
    guids_by_name: dict[str, list[int]]
    button_component_guids: set[int]


def build_backfill_ui_record_index_from_record_list(record_list: list[object]) -> BackfillUiRecordIndex | None:
    """Build a minimized index from dump-json UI record list."""
    name_by_guid: dict[int, str] = {}
    parent_by_guid: dict[int, int | None] = {}
    children_by_parent: dict[int, list[int]] = {}
    guids_by_name: dict[str, list[int]] = {}
    button_guids: set[int] = set()

    any_guid = False
    for r0 in record_list:
        if not isinstance(r0, dict):
            continue

        primary_guid = _extract_ui_record_primary_guid(r0)
        if primary_guid is None or int(primary_guid) <= 0:
            continue
        any_guid = True

        parent_value = r0.get("504")
        parent_guid = int(parent_value) if isinstance(parent_value, int) else None
        parent_by_guid[int(primary_guid)] = parent_guid
        if parent_guid is not None:
            children_by_parent.setdefault(int(parent_guid), []).append(int(primary_guid))

        nm = _extract_ui_record_primary_name(r0)
        if nm is not None and str(nm) != "":
            name_by_guid[int(primary_guid)] = str(nm)
            guids_by_name.setdefault(str(nm), []).append(int(primary_guid))

        if _ui_record_has_button_component(r0):
            button_guids.add(int(primary_guid))

    if not any_guid:
        return None

    return BackfillUiRecordIndex(
        name_by_guid=dict(name_by_guid),
        parent_by_guid=dict(parent_by_guid),
        children_by_parent={k: sorted(v) for k, v in children_by_parent.items()},
        guids_by_name={k: sorted(v) for k, v in guids_by_name.items()},
        button_component_guids=set(button_guids),
    )


def infer_root_layout_name_for_guid(
    *,
    guid: int,
    parent_by_guid: dict[int, int | None],
    name_by_guid: dict[int, str],
    cache: dict[int, str | None],
) -> str | None:
    """Infer root layout name for a guid by walking parent links."""
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


def resolve_ui_key_guid_from_output_gil_for_backfill(
    *,
    ui_key: str,
    layout_name_hint: str | None,
    ui_index: BackfillUiRecordIndex,
    root_name_cache: dict[int, str | None],
) -> int | None:
    """Resolve ui_key placeholder into guid using the minimized index."""
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
            if int(child_guid) in ui_index.button_component_guids:
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

    if tail_last == "group":
        state_parts = suffix_parts[:-1]
        group_suffix = data_ui_key if not state_parts else f"{data_ui_key}__{'__'.join(state_parts)}"
        return _find_group_guid(group_suffix)

    if tail_last == "btn_item":
        state_parts = suffix_parts[:-1]
        if state_parts:
            group_suffix = f"{data_ui_key}__{'__'.join(state_parts)}"
            group_guid = _find_group_guid(group_suffix)
            if group_guid is None:
                return None
            btn_item_guid = _find_btn_item_under_group(int(group_guid))
            return int(btn_item_guid) if btn_item_guid is not None else int(group_guid)

        group_guid = _find_group_guid(data_ui_key)
        if group_guid is not None:
            btn_item_guid = _find_btn_item_under_group(int(group_guid))
            return int(btn_item_guid) if btn_item_guid is not None else int(group_guid)

        group_guid2 = _find_group_guid(data_ui_key + "_state")
        if group_guid2 is not None:
            btn_item_guid2 = _find_btn_item_under_group(int(group_guid2))
            return int(btn_item_guid2) if btn_item_guid2 is not None else int(group_guid2)

        want_root = str(layout_name_hint or "").strip()
        prefix_variants = [f"组件组_{data_ui_key}__", f"组件组_{data_ui_key}_state__"]
        prefer_state_prefixes = ["unselected", "enabled", "normal"]
        best_rank: tuple[int, int] | None = None
        best_btn_item: int | None = None

        for record_name, guids in ui_index.guids_by_name.items():
            if not isinstance(record_name, str) or not record_name.startswith("组件组_"):
                continue
            if want_root != "":
                guids2 = _filter_by_layout(list(guids))
                if not guids2:
                    continue
            else:
                guids2 = list(guids)

            if not any(record_name.startswith(pfx) for pfx in prefix_variants):
                continue

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


def iter_all_layout_root_names(*, ui_index: BackfillUiRecordIndex) -> Iterable[str]:
    """Iterate all layout root names in the index."""
    for guid, parent in ui_index.parent_by_guid.items():
        if parent is None:
            name = ui_index.name_by_guid.get(int(guid))
            if isinstance(name, str) and name != "":
                yield str(name)

