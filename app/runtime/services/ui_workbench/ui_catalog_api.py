from __future__ import annotations


def build_ui_catalog_payload(*, current_package_id: str, management: object) -> dict:
    """返回当前项目存档的 UI 布局/模板清单（用于 Web 侧浏览与预览）。"""
    layouts: list[dict[str, object]] = []
    templates: list[dict[str, object]] = []

    ui_layouts: dict = getattr(management, "ui_layouts", {}) or {}
    for layout_id, payload in ui_layouts.items():
        if not isinstance(payload, dict):
            continue
        layout_name = str(payload.get("layout_name", "") or payload.get("name", "") or layout_id)
        builtin = payload.get("builtin_widgets", [])
        custom = payload.get("custom_groups", [])
        layouts.append(
            {
                "layout_id": str(layout_id),
                "layout_name": layout_name,
                "builtin_count": len(builtin) if isinstance(builtin, list) else 0,
                "custom_count": len(custom) if isinstance(custom, list) else 0,
            }
        )

    ui_templates: dict = getattr(management, "ui_widget_templates", {}) or {}
    for template_id, payload in ui_templates.items():
        if not isinstance(payload, dict):
            continue
        template_name = str(payload.get("template_name", "") or payload.get("name", "") or template_id)
        widgets = payload.get("widgets", [])
        templates.append(
            {
                "template_id": str(template_id),
                "template_name": template_name,
                "widget_count": len(widgets) if isinstance(widgets, list) else 0,
                "is_combination": bool(payload.get("is_combination", False)),
                "is_builtin": str(template_id).startswith("builtin_"),
            }
        )

    layouts.sort(key=lambda item: str(item.get("layout_name", "")).casefold())
    templates.sort(key=lambda item: str(item.get("template_name", "")).casefold())

    return {
        "ok": True,
        "current_package_id": str(current_package_id or ""),
        "layouts": layouts,
        "templates": templates,
    }


def get_ui_layout_payload(*, current_package_id: str, management: object, layout_id: str) -> dict:
    ui_layouts: dict = getattr(management, "ui_layouts", {}) or {}
    payload = ui_layouts.get(layout_id)
    if not isinstance(payload, dict):
        raise RuntimeError(f"未找到 UI 布局: {layout_id}")
    return {"ok": True, "current_package_id": str(current_package_id or ""), "layout": payload}


def get_ui_template_payload(*, current_package_id: str, management: object, template_id: str) -> dict:
    ui_templates: dict = getattr(management, "ui_widget_templates", {}) or {}
    payload = ui_templates.get(template_id)
    if not isinstance(payload, dict):
        raise RuntimeError(f"未找到 UI 控件模板: {template_id}")
    return {"ok": True, "current_package_id": str(current_package_id or ""), "template": payload}


__all__ = [
    "build_ui_catalog_payload",
    "get_ui_layout_payload",
    "get_ui_template_payload",
]

