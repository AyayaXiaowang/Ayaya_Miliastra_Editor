from __future__ import annotations

from datetime import datetime
from typing import Protocol

from engine.configs.components.ui_control_group_model import (
    BUILTIN_WIDGET_TYPES,
    UIControlGroupTemplate,
    UIWidgetConfig,
    UILayout,
    create_builtin_widget_templates,
)
from engine.configs.resource_types import ResourceType

from .naming import collect_existing_names, ensure_unique_name, generate_unique_id
from .types import ImportBundleResult, ImportResult


class UniqueIdGenerator(Protocol):
    def __call__(self, *, prefix: str, existing: set[str]) -> str: ...


class UniqueNameEnsurer(Protocol):
    def __call__(self, *, desired: str, existing_names: set[str]) -> str: ...


def ensure_management_ui_dicts(*, management: object) -> tuple[dict, dict]:
    """确保 management 持有可写的 ui_widget_templates / ui_layouts 字典，并返回它们。"""
    ui_widget_templates = getattr(management, "ui_widget_templates", None)
    if not isinstance(ui_widget_templates, dict):
        ui_widget_templates = {}
        setattr(management, "ui_widget_templates", ui_widget_templates)

    ui_layouts = getattr(management, "ui_layouts", None)
    if not isinstance(ui_layouts, dict):
        ui_layouts = {}
        setattr(management, "ui_layouts", ui_layouts)

    return ui_widget_templates, ui_layouts


def ensure_builtin_widget_templates(
    *,
    ui_widget_templates: dict,
    current_package_id: str,
    now_iso: str,
) -> list[str]:
    """补齐固有控件模板（按包后缀化优先），并返回 layout.builtin_widgets 列表。"""
    current_package_id_text = str(current_package_id or "").strip()
    if not current_package_id_text:
        raise ValueError("current_package_id is required")

    builtin_base_templates = create_builtin_widget_templates()

    builtin_widgets: list[str] = []
    for widget_type in list(BUILTIN_WIDGET_TYPES):
        preferred_template_id = f"builtin_{widget_type}__{current_package_id_text}"
        legacy_template_id = f"builtin_{widget_type}"

        if preferred_template_id in ui_widget_templates:
            builtin_widgets.append(preferred_template_id)
            continue
        if legacy_template_id in ui_widget_templates:
            builtin_widgets.append(legacy_template_id)
            continue

        # 缺失时补齐：用引擎内建默认位置/大小作为兜底，并将 ID 后缀化为 __<package_id>
        base_template = builtin_base_templates.get(legacy_template_id)
        if base_template is None:
            continue

        payload = base_template.serialize()
        payload["template_id"] = preferred_template_id
        payload["template_name"] = widget_type
        payload["created_at"] = now_iso
        payload["updated_at"] = now_iso

        widgets_payload = payload.get("widgets")
        if isinstance(widgets_payload, list):
            for widget_payload_item in widgets_payload:
                if not isinstance(widget_payload_item, dict):
                    continue
                widget_payload_item["widget_id"] = f"builtin_{widget_type}_widget__{current_package_id_text}"
                widget_payload_item["widget_type"] = widget_type
                widget_payload_item["widget_name"] = widget_type
                widget_payload_item["is_builtin"] = True

        ui_widget_templates[preferred_template_id] = payload
        builtin_widgets.append(preferred_template_id)

    return builtin_widgets


def _normalize_existing_ids(raw: object) -> set[str]:
    if not isinstance(raw, dict):
        return set()
    out: set[str] = set()
    for k in raw.keys():
        key = str(k or "").strip()
        if key:
            out.add(key)
    return out


def _collect_existing_resource_ids(*, resource_manager: object, resource_type: ResourceType) -> set[str]:
    list_func = getattr(resource_manager, "list_resource_file_paths", None)
    if not callable(list_func):
        raise RuntimeError("resource_manager 缺少 list_resource_file_paths(ResourceType) 方法")
    mapping = list_func(resource_type)
    return _normalize_existing_ids(mapping)


def _rect_of_widget(widget_obj: UIWidgetConfig) -> tuple[float, float, float, float]:
    x, y = widget_obj.position
    w, h = widget_obj.size
    return float(x), float(y), float(w), float(h)


def _rect_area(rect: tuple[float, float, float, float]) -> float:
    _x, _y, w, h = rect
    if w <= 0 or h <= 0:
        return 0.0
    return float(w) * float(h)


def _rect_intersection_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)
    iw = right - left
    ih = bottom - top
    if iw <= 0 or ih <= 0:
        return 0.0
    return float(iw) * float(ih)


def _rect_contains_point(rect: tuple[float, float, float, float], px: float, py: float) -> bool:
    x, y, w, h = rect
    return (px >= x) and (py >= y) and (px <= x + w) and (py <= y + h)


def _rect_center(rect: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = rect
    return x + w / 2.0, y + h / 2.0


def _bounds_of_widgets(widget_list: list[UIWidgetConfig]) -> tuple[float, float, float, float]:
    if not widget_list:
        return 0.0, 0.0, 0.0, 0.0
    min_x = min(float(w.position[0]) for w in widget_list)
    min_y = min(float(w.position[1]) for w in widget_list)
    max_x = max(float(w.position[0] + w.size[0]) for w in widget_list)
    max_y = max(float(w.position[1] + w.size[1]) for w in widget_list)
    return min_x, min_y, max(0.0, max_x - min_x), max(0.0, max_y - min_y)


def _clone_widget_with_new_id(source_widget: UIWidgetConfig, *, new_widget_id: str) -> UIWidgetConfig:
    widget_payload = source_widget.serialize()
    widget_payload["widget_id"] = new_widget_id
    widget_payload["is_builtin"] = False
    return UIWidgetConfig.deserialize(widget_payload)


def import_layout_from_template_payload(
    *,
    current_package_id: str,
    management: object,
    resource_manager: object,
    layout_name: str,
    template_payload: dict,
    now_iso: str | None = None,
    id_generator: UniqueIdGenerator = generate_unique_id,
    name_ensurer: UniqueNameEnsurer = ensure_unique_name,
) -> ImportResult:
    """导入 Workbench 的单模板 payload，并写入 management（不负责保存落盘）。"""
    current_package_id_text = str(current_package_id or "").strip()
    if not current_package_id_text or current_package_id_text == "global_view":
        raise ValueError("current_package_id is required and cannot be global_view")

    ui_widget_templates, ui_layouts = ensure_management_ui_dicts(management=management)

    now = str(now_iso or datetime.now().isoformat())

    existing_layout_ids = _collect_existing_resource_ids(
        resource_manager=resource_manager, resource_type=ResourceType.UI_LAYOUT
    )
    existing_template_ids = _collect_existing_resource_ids(
        resource_manager=resource_manager, resource_type=ResourceType.UI_WIDGET_TEMPLATE
    )
    existing_layout_ids |= _normalize_existing_ids(ui_layouts)
    existing_template_ids |= _normalize_existing_ids(ui_widget_templates)

    layout_id = id_generator(prefix="layout_html", existing=existing_layout_ids)
    existing_layout_ids.add(layout_id)
    template_id = id_generator(prefix="ui_widget_template_html", existing=existing_template_ids)
    existing_template_ids.add(template_id)

    normalized_layout_name = name_ensurer(
        desired=str(layout_name or "").strip() or "HTML导入_界面布局",
        existing_names=collect_existing_names(ui_layouts, "layout_name"),
    )
    normalized_template_name = name_ensurer(
        desired=f"{normalized_layout_name}（HTML组合）",
        existing_names=collect_existing_names(ui_widget_templates, "template_name"),
    )

    template_obj = UIControlGroupTemplate.deserialize(template_payload)
    if template_obj is None:
        raise RuntimeError("导入失败：模板 JSON 缺少 template_id（不是合法的 UIControlGroupTemplate）。")

    template_obj.template_id = template_id
    template_obj.template_name = normalized_template_name
    template_obj.created_at = now
    template_obj.updated_at = now

    # 保留原始 widget_id（便于排查），并重写为全局唯一
    for idx, widget in enumerate(list(template_obj.widgets)):
        old_widget_id = str(getattr(widget, "widget_id", "") or "")
        if old_widget_id:
            widget.extra.setdefault("__source_widget_id", old_widget_id)
        widget.widget_id = f"{template_id}_w{idx:03d}"
        widget.is_builtin = False

    builtin_widgets = ensure_builtin_widget_templates(
        ui_widget_templates=ui_widget_templates,
        current_package_id=current_package_id_text,
        now_iso=now,
    )

    # 写入组合模板（用于溯源/整体预览），但布局默认引用“拆分后的单控件模板”
    ui_widget_templates[template_id] = template_obj.serialize()

    existing_template_names = collect_existing_names(ui_widget_templates, "template_name")
    custom_group_entries: list[tuple[int, str]] = []  # (sort_key(min_layer_index), template_id)

    # 以 layer_index 升序稳定排序（背景→前景），避免导入后列表顺序随机
    source_widgets = sorted(
        list(template_obj.widgets),
        key=lambda w: int(getattr(w, "layer_index", 0) or 0),
    )

    # 1) “按钮打组”：以 <button> 导出的交互层（道具展示）作为锚点，将其底色/阴影/边框/文本聚合成一个组合模板。
    button_anchors = [
        w
        for w in source_widgets
        if (str(getattr(w, "widget_type", "") or "") == "道具展示")
        and (not bool(getattr(w, "is_builtin", False)))
    ]
    widgets_in_button_groups: set[str] = set()
    group_members_by_anchor_id: dict[str, list[UIWidgetConfig]] = {}
    for anchor in button_anchors:
        group_members_by_anchor_id[anchor.widget_id] = [anchor]
        widgets_in_button_groups.add(anchor.widget_id)

    # 将进度条/文本框按几何关系归属到某个按钮锚点（只聚合 Workbench 约定前缀，避免把大背景误并入按钮组）
    progress_prefixes = ("按钮_", "阴影_", "边框_")
    text_prefix = "文本_"

    anchor_rect_cache: dict[str, tuple[float, float, float, float]] = {}
    anchor_area_cache: dict[str, float] = {}
    for anchor in button_anchors:
        rect = _rect_of_widget(anchor)
        anchor_rect_cache[anchor.widget_id] = rect
        anchor_area_cache[anchor.widget_id] = _rect_area(rect)

    for w in source_widgets:
        if w.widget_id in widgets_in_button_groups:
            continue
        if bool(getattr(w, "is_builtin", False)):
            continue

        widget_type = str(getattr(w, "widget_type", "") or "")
        widget_name = str(getattr(w, "widget_name", "") or "")
        if widget_type not in {"进度条", "文本框"}:
            continue

        w_rect = _rect_of_widget(w)
        if _rect_area(w_rect) <= 0:
            continue

        # 候选筛选：仅考虑“看起来是按钮堆叠的一部分”的控件
        if widget_type == "进度条":
            if not widget_name.startswith(progress_prefixes):
                continue
        if widget_type == "文本框":
            if not widget_name.startswith(text_prefix):
                continue

        best_anchor: UIWidgetConfig | None = None
        best_intersection = 0.0
        for anchor in button_anchors:
            a_rect = anchor_rect_cache.get(anchor.widget_id)
            if a_rect is None:
                continue
            area = _rect_intersection_area(w_rect, a_rect)
            if area <= best_intersection:
                continue
            best_intersection = area
            best_anchor = anchor

        if best_anchor is None or best_intersection <= 0:
            continue

        a_rect = anchor_rect_cache.get(best_anchor.widget_id)
        if a_rect is None:
            continue

        # 几何约束（避免误分组）：
        # - 文本：中心点必须落在按钮范围内
        # - 进度条：中心点在按钮内（底色/边框），或按钮中心点在其内（阴影）
        wx, wy = _rect_center(w_rect)
        ax, ay = _rect_center(a_rect)
        if widget_type == "文本框":
            if not _rect_contains_point(a_rect, wx, wy):
                continue
        else:
            if not (_rect_contains_point(a_rect, wx, wy) or _rect_contains_point(w_rect, ax, ay)):
                continue
            # 阴影允许略大，但禁止“超大背景”被并入按钮组
            button_area = anchor_area_cache.get(best_anchor.widget_id, 0.0)
            if button_area > 0:
                if _rect_area(w_rect) > button_area * 6.0:
                    continue

        group_members_by_anchor_id[best_anchor.widget_id].append(w)
        widgets_in_button_groups.add(w.widget_id)

    # 生成按钮组合模板（一个按钮 = 一个模板）
    for button_index, anchor in enumerate(button_anchors):
        members = group_members_by_anchor_id.get(anchor.widget_id, [])
        if not members:
            continue

        new_template_id = id_generator(prefix=f"{template_id}_btn", existing=existing_template_ids)
        existing_template_ids.add(new_template_id)

        # 模板名：尽量使用 aria-label / data-debug-label；否则回退 widget_name
        debug_label = ""
        if isinstance(getattr(anchor, "extra", None), dict):
            debug_label = str(
                anchor.extra.get("_html_data_debug_label") or anchor.extra.get("_html_button_aria_label") or ""
            ).strip()
        fallback_name = str(getattr(anchor, "widget_name", "") or "").strip()
        label_text = debug_label or fallback_name or f"按钮_{button_index:03d}"
        if label_text.startswith("按钮_道具展示_"):
            label_text = label_text[len("按钮_道具展示_") :]
        desired_template_name = (
            f"{normalized_layout_name}_按钮_{label_text}"
            if label_text
            else f"{normalized_layout_name}_按钮_{button_index:03d}"
        )
        normalized_child_name = name_ensurer(desired=desired_template_name, existing_names=existing_template_names)
        existing_template_names.add(normalized_child_name)

        # 组内 widget 也按 layer_index 排序，保证点击/遮挡顺序稳定
        members_sorted = sorted(members, key=lambda w: int(getattr(w, "layer_index", 0) or 0))
        cloned_widgets: list[UIWidgetConfig] = []
        for idx, src_widget in enumerate(members_sorted):
            widget_obj = _clone_widget_with_new_id(src_widget, new_widget_id=f"{new_template_id}_w{idx:03d}")
            cloned_widgets.append(widget_obj)

        gx, gy, gw, gh = _bounds_of_widgets(cloned_widgets)
        child_template = UIControlGroupTemplate(
            template_id=new_template_id,
            template_name=normalized_child_name,
            is_combination=True,
            widgets=cloned_widgets,
            group_position=(gx, gy),
            group_size=(gw, gh),
            supports_layout_visibility_override=True,
            description="由 UI 工作台（HTML）导入生成：按钮已打组（道具展示+底色+阴影+文本等）。",
            created_at=now,
            updated_at=now,
            extra={"__html_import_group_template_id": template_id, "__html_group_kind": "button"},
        )
        ui_widget_templates[new_template_id] = child_template.serialize()
        min_layer = min(int(getattr(w, "layer_index", 0) or 0) for w in members_sorted) if members_sorted else 0
        custom_group_entries.append((min_layer, new_template_id))

    # 2) 其余控件：保持“单控件模板”语义，便于在布局详情中逐项查看与调整
    for widget_index, source_widget in enumerate(source_widgets):
        if source_widget.widget_id in widgets_in_button_groups:
            continue

        new_template_id = id_generator(prefix=f"{template_id}_part", existing=existing_template_ids)
        existing_template_ids.add(new_template_id)

        widget_obj = _clone_widget_with_new_id(source_widget, new_widget_id=f"{new_template_id}_w000")
        base_name = str(getattr(widget_obj, "widget_name", "") or "").strip() or str(
            getattr(widget_obj, "widget_type", "") or ""
        ).strip()
        desired_template_name = (
            f"{normalized_layout_name}_{base_name}"
            if base_name
            else f"{normalized_layout_name}_控件_{widget_index:03d}"
        )
        normalized_child_name = name_ensurer(desired=desired_template_name, existing_names=existing_template_names)
        existing_template_names.add(normalized_child_name)

        child_template = UIControlGroupTemplate(
            template_id=new_template_id,
            template_name=normalized_child_name,
            is_combination=False,
            widgets=[widget_obj],
            group_position=tuple(widget_obj.position),
            group_size=tuple(widget_obj.size),
            supports_layout_visibility_override=True,
            description="由 UI 工作台（HTML）拆分导入生成（单控件模板）。",
            created_at=now,
            updated_at=now,
            extra={"__html_import_group_template_id": template_id, "__html_group_kind": "single"},
        )
        ui_widget_templates[new_template_id] = child_template.serialize()
        custom_group_entries.append((int(getattr(widget_obj, "layer_index", 0) or 0), new_template_id))

    # 稳定排序：背景→前景
    custom_group_entries.sort(key=lambda pair: (pair[0], pair[1]))
    custom_group_template_ids = [tid for _layer, tid in custom_group_entries]

    layout_obj = UILayout(
        layout_id=layout_id,
        layout_name=normalized_layout_name,
        builtin_widgets=builtin_widgets,
        custom_groups=custom_group_template_ids,
        default_for_player="所有玩家",
        description="由 UI 工作台（HTML）导入生成（按钮已打组，其余控件为单控件模板）。",
        created_at=now,
        updated_at=now,
        visibility_overrides={},
    )
    ui_layouts[layout_id] = layout_obj.serialize()

    return ImportResult(
        layout_id=layout_id,
        layout_name=normalized_layout_name,
        template_id=template_id,
        template_name=normalized_template_name,
        template_count=len(custom_group_template_ids),
        widget_count=len(template_obj.widgets),
    )


def import_layout_from_bundle_payload(
    *,
    current_package_id: str,
    management: object,
    resource_manager: object,
    layout_name: str,
    bundle_payload: dict,
    now_iso: str | None = None,
    id_generator: UniqueIdGenerator = generate_unique_id,
    name_ensurer: UniqueNameEnsurer = ensure_unique_name,
) -> ImportBundleResult:
    """导入 Workbench 导出的 bundle（UILayout + 多个 template），并写入 management（不负责保存落盘）。"""
    current_package_id_text = str(current_package_id or "").strip()
    if not current_package_id_text or current_package_id_text == "global_view":
        raise ValueError("current_package_id is required and cannot be global_view")

    if not isinstance(bundle_payload, dict):
        raise RuntimeError("导入失败：bundle 必须是对象")

    bundle_layout = bundle_payload.get("layout", None)
    if not isinstance(bundle_layout, dict):
        raise RuntimeError("导入失败：bundle.layout 必须是对象（UILayout）。")

    raw_templates = bundle_payload.get("templates", None)
    templates_payload_list: list[dict] = []
    if isinstance(raw_templates, list):
        for item in raw_templates:
            if isinstance(item, dict):
                templates_payload_list.append(item)
    elif isinstance(raw_templates, dict):
        for _key, item in raw_templates.items():
            if isinstance(item, dict):
                templates_payload_list.append(item)
    else:
        raise RuntimeError("导入失败：bundle.templates 必须是数组或对象（template_id -> payload）。")

    if not templates_payload_list:
        raise RuntimeError("导入失败：bundle.templates 为空。")

    ui_widget_templates, ui_layouts = ensure_management_ui_dicts(management=management)

    now = str(now_iso or datetime.now().isoformat())

    existing_layout_ids = _collect_existing_resource_ids(
        resource_manager=resource_manager, resource_type=ResourceType.UI_LAYOUT
    )
    existing_template_ids = _collect_existing_resource_ids(
        resource_manager=resource_manager, resource_type=ResourceType.UI_WIDGET_TEMPLATE
    )
    existing_layout_ids |= _normalize_existing_ids(ui_layouts)
    existing_template_ids |= _normalize_existing_ids(ui_widget_templates)

    layout_id = id_generator(prefix="layout_html", existing=existing_layout_ids)
    existing_layout_ids.add(layout_id)

    desired_layout_name = str(layout_name or "").strip()
    if not desired_layout_name:
        desired_layout_name = str(
            bundle_layout.get("layout_name", "") or bundle_layout.get("name", "") or ""
        ).strip()
    if not desired_layout_name:
        desired_layout_name = "HTML导入_界面布局"

    normalized_layout_name = name_ensurer(
        desired=desired_layout_name,
        existing_names=collect_existing_names(ui_layouts, "layout_name"),
    )

    builtin_widgets = ensure_builtin_widget_templates(
        ui_widget_templates=ui_widget_templates,
        current_package_id=current_package_id_text,
        now_iso=now,
    )

    existing_template_names = collect_existing_names(ui_widget_templates, "template_name")
    template_id_map: dict[str, str] = {}
    imported_widget_count = 0

    # 写入 bundle templates
    for raw_template_payload in templates_payload_list:
        template_obj = UIControlGroupTemplate.deserialize(raw_template_payload)
        if template_obj is None:
            raise RuntimeError("导入失败：bundle.templates 内存在缺少 template_id 的条目。")

        old_template_id = str(getattr(template_obj, "template_id", "") or "").strip()
        new_template_id = id_generator(prefix="ui_widget_template_html", existing=existing_template_ids)
        existing_template_ids.add(new_template_id)

        template_obj.template_id = new_template_id

        desired_template_name = (
            str(getattr(template_obj, "template_name", "") or "").strip() or old_template_id or new_template_id
        )
        normalized_template_name = name_ensurer(
            desired=desired_template_name,
            existing_names=existing_template_names,
        )
        existing_template_names.add(normalized_template_name)
        template_obj.template_name = normalized_template_name

        template_obj.created_at = now
        template_obj.updated_at = now

        # 保留原始 widget_id（便于排查），并重写为全局唯一
        for idx, widget in enumerate(list(template_obj.widgets)):
            old_widget_id = str(getattr(widget, "widget_id", "") or "")
            if old_widget_id:
                widget.extra.setdefault("__source_widget_id", old_widget_id)
            widget.widget_id = f"{new_template_id}_w{idx:03d}"
            widget.is_builtin = False

        imported_widget_count += len(template_obj.widgets)
        ui_widget_templates[new_template_id] = template_obj.serialize()
        if old_template_id:
            template_id_map[old_template_id] = new_template_id

    # 生成 layout.custom_groups（优先用 bundle 的顺序）
    raw_custom_groups = bundle_layout.get("custom_groups", [])
    if not isinstance(raw_custom_groups, list):
        raw_custom_groups = []

    custom_groups: list[str] = []
    if raw_custom_groups:
        for old_id_value in raw_custom_groups:
            old_id = str(old_id_value or "").strip()
            if not old_id:
                continue
            new_id = template_id_map.get(old_id)
            if not new_id:
                raise RuntimeError(f"导入失败：layout.custom_groups 引用了不存在的模板: {old_id}")
            custom_groups.append(new_id)
    else:
        custom_groups = list(template_id_map.values())

    default_for_player = str(bundle_layout.get("default_for_player") or "所有玩家")
    description = str(bundle_layout.get("description") or "由 UI 工作台（HTML）导入生成（bundle）。")

    layout_obj = UILayout(
        layout_id=layout_id,
        layout_name=normalized_layout_name,
        builtin_widgets=builtin_widgets,
        custom_groups=custom_groups,
        default_for_player=default_for_player,
        description=description,
        created_at=now,
        updated_at=now,
        visibility_overrides={},
    )
    ui_layouts[layout_id] = layout_obj.serialize()

    return ImportBundleResult(
        layout_id=layout_id,
        layout_name=normalized_layout_name,
        template_count=len(template_id_map),
        widget_count=imported_widget_count,
    )


__all__ = [
    "UniqueIdGenerator",
    "UniqueNameEnsurer",
    "ensure_builtin_widget_templates",
    "ensure_management_ui_dicts",
    "import_layout_from_bundle_payload",
    "import_layout_from_template_payload",
]

