from __future__ import annotations

import copy
from typing import Any, Dict

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    append_children_guids_to_parent_record as _append_children_guids_to_parent_record,
    force_record_to_group_container_shape as _force_record_to_group_container_shape,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    set_children_guids_to_parent_record as _set_children_guids_to_parent_record,
    set_widget_name as _set_widget_name,
)
from .web_ui_import_constants import UI_KEY_GROUP_TAIL_DUP_RE, UI_KEY_GROUP_TAIL_RECT_RE
from .web_ui_import_rect import has_rect_transform_state


def infer_ui_component_group_key(ui_key: str) -> str:
    """
    将 widget 的 ui_key 归一化为“组件组 key”（同一 HTML 元素的 shadow/border/rect/text/... 归为同组）。

    Workbench 约定（示例）：
      <prefix>__<base>__<kind>
      <prefix>__<base>__<kind>__rX_Y_W_H        # cutout 切分后的稳定 rect 后缀
      <prefix>__<base>__<kind>__dup(_N)         # 兜底去重后缀

    组 key 的策略：
    - 先剥掉尾部的 rect/dup 去重后缀
    - 再剥掉最后一个 kind token
    """
    raw = str(ui_key or "").strip()
    if raw == "":
        return ""
    parts = [p for p in raw.split("__") if p != ""]
    if len(parts) <= 1:
        return raw

    while parts and (UI_KEY_GROUP_TAIL_RECT_RE.match(parts[-1]) or UI_KEY_GROUP_TAIL_DUP_RE.match(parts[-1])):
        parts.pop()
    if len(parts) <= 1:
        return raw

    # strip kind
    parts.pop()
    if not parts:
        return raw
    return "__".join(parts)


def get_atomic_component_group_key(widget: Dict[str, Any]) -> str:
    """
    原子组 key（最小集合）：
    - 必须来自同一个 HTML 元素/组件
    - 绝不允许依赖 class/dataLabel 等“外观画像”，否则会把不同按钮误合并
    - 优先使用前端导出的 `__html_component_key`
    - 兜底才从 ui_key 推导（兼容旧 bundle）
    """
    raw = widget.get("__html_component_key")
    if isinstance(raw, str) and raw.strip():
        return str(raw).strip()
    ui_key = str(widget.get("ui_key") or "").strip()
    if ui_key:
        return infer_ui_component_group_key(ui_key)
    return ""


def strip_ui_key_prefix_for_group_name(group_key: str) -> str:
    parts = [p for p in str(group_key or "").split("__") if p != ""]
    if not parts:
        return str(group_key or "")
    # page_prefix__base -> base
    if len(parts) >= 2:
        return parts[-1]
    return parts[0]


def remove_child_from_parent_children(parent_record: Dict[str, Any], child_guid: int) -> bool:
    """
    从 parent_record.children(varint list) 中移除 child_guid（若存在），返回是否发生移除。
    """
    children = _get_children_guids_from_parent_record(parent_record)
    if int(child_guid) not in children:
        return False
    new_children = [int(g) for g in children if int(g) != int(child_guid)]
    _set_children_guids_to_parent_record(parent_record, new_children)
    return True


def ensure_child_in_parent_children(parent_record: Dict[str, Any], child_guid: int) -> None:
    children = _get_children_guids_from_parent_record(parent_record)
    if int(child_guid) in children:
        return
    _append_children_guids_to_parent_record(parent_record, [int(child_guid)])


def is_name_writable_ui_record(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 1:
        return False
    name_component = component_list[0]
    if not isinstance(name_component, dict):
        return False
    node12 = name_component.get("12")
    return isinstance(node12, dict)


def ensure_list_min_len(container: Dict[str, Any], field_key: str, min_len: int) -> list:
    current = container.get(field_key)
    if current is None:
        current = []
        container[field_key] = current
    if not isinstance(current, list):
        # 兼容：部分基底 dump 的 repeated 字段可能退化为标量/dict；组容器写回允许直接覆盖为 list 形态。
        current = []
        container[field_key] = current
    while len(current) < int(min_len):
        current.append({})
    return current


def is_group_container_record_shape(record: Any) -> bool:
    """
    参考 `save/界面控件组/打组.gil` / `save/界面控件组/全是进度条组合.gil`：
    - 组容器 record 的 component_list(505) 只有 2 个元素（没有 RectTransform）
    - 组容器 record 的 meta_list(502) 至少包含 2 个元素
    - 组容器 record 可写入名字（505[0]/12 为 dict）
    """
    if not isinstance(record, dict):
        return False
    meta_list = record.get("502")
    if not isinstance(meta_list, list) or len(meta_list) < 2:
        return False
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) != 2:
        return False
    c0 = component_list[0]
    if not isinstance(c0, dict):
        return False
    node12 = c0.get("12")
    if not isinstance(node12, dict):
        return False
    # 关键护栏：component[1] 必须存在且形态有效，否则写回后该 record 会退化为“只有名字组件”，
    # 在编辑器侧表现为“模板实例空白/不可用”。
    c1 = component_list[1]
    if not isinstance(c1, dict) or not c1:
        return False
    if "14" not in c1:
        return False
    if has_rect_transform_state(record, state_index=0):
        return False
    return True


def build_group_container_record(*, group_guid: int, parent_guid: int, group_name: str) -> Dict[str, Any]:
    """
    构造一个“纯组容器”record（不携带任何控件样式/RectTransform）。
    """
    return build_group_container_record_from_prototype(
        prototype_record=None,
        group_guid=int(group_guid),
        parent_guid=int(parent_guid),
        group_name=str(group_name),
    )


def build_group_container_record_from_prototype(
    *,
    prototype_record: Dict[str, Any] | None,
    group_guid: int,
    parent_guid: int,
    group_name: str,
) -> Dict[str, Any]:
    """
    基底兼容：优先从 base `.gil` 中挑选一个“组容器 record”作为原型来 clone。

    背景：
    - 不同存档的组容器 meta_list/component_list 形态可能不同（例如 meta_len=2 vs meta_len=4）。
    - 若强行用固定样本形态写回，编辑器侧可能无法打开（或丢层级/表现异常）。
    """
    if prototype_record is None:
        record: Dict[str, Any] = {
            "501": int(group_guid),
            "504": int(parent_guid),
            "502": [{}, {}],
            "505": [{"12": {"501": ""}, "501": 2, "502": 15}, {}],
        }
        _force_record_to_group_container_shape(record)
        meta_list = record.get("502")
        if not isinstance(meta_list, list) or len(meta_list) < 2:
            raise RuntimeError("internal error: group record meta list not initialized")
        meta_list[1] = {"11": {"501": int(group_guid)}, "501": 1, "502": 5}
        _set_widget_name(record, str(group_name))
        return record

    # clone from prototype
    record = copy.deepcopy(prototype_record)
    old_guid_raw = record.get("501")
    old_guid = int(old_guid_raw) if isinstance(old_guid_raw, int) else 0
    record["501"] = int(group_guid)
    record["504"] = int(parent_guid)

    # 清空 children（保持原型的 503 字段形态：str / list[str] / 缺失 皆可）
    _set_children_guids_to_parent_record(record, [])

    # 仅替换“自指 GUID”常见位置：meta blob 中的 {"11": {"501": <guid>}}
    # （避免粗暴替换所有 int 造成误伤。）
    if old_guid > 0 and int(old_guid) != int(group_guid):

        def _rewrite_meta_self_guid(node: Any) -> None:
            if isinstance(node, dict):
                v11 = node.get("11")
                if isinstance(v11, dict) and v11.get("501") == int(old_guid):
                    v11["501"] = int(group_guid)
                for v in node.values():
                    _rewrite_meta_self_guid(v)
            elif isinstance(node, list):
                for v in node:
                    _rewrite_meta_self_guid(v)

        _rewrite_meta_self_guid(record.get("502"))

    _set_widget_name(record, str(group_name))

    # 最终护栏：确保仍是“组容器 record”形态
    # 额外护栏：某些基底存档的“组容器”record 可能存在 component[1] 为空的异常形态；
    # 若直接 clone 会导致写回后的 record 退化为“只有名字组件”（编辑器侧空白）。
    # 这里在不强制覆盖 meta 结构的前提下，最小化补齐 component[1]。
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 2:
        raise RuntimeError("group container prototype clone produced invalid component_list at field 505")
    c1 = component_list[1]
    if not isinstance(c1, dict) or not c1 or "14" not in c1:
        from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import GROUP_CONTAINER_COMPONENT1 as _C1

        component_list[1] = copy.deepcopy(_C1)
    if not is_group_container_record_shape(record):
        raise RuntimeError("group container prototype clone produced non-group-container record")

    return record

