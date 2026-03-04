from __future__ import annotations

from pathlib import Path


class _UiWorkbenchBridgeUiCatalogMixin:
    # --------------------------------------------------------------------- app ui catalog (web-first)
    def get_ui_catalog_payload(self) -> dict:
        """返回当前项目存档的 UI 布局/模板清单（用于 Web 侧浏览与预览）。"""
        current_package_id, _package, management = self._get_current_management_or_raise()

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
            "current_package_id": current_package_id,
            "layouts": layouts,
            "templates": templates,
        }

    def get_ui_layout_payload(self, layout_id: str) -> dict:
        current_package_id, _package, management = self._get_current_management_or_raise()
        ui_layouts: dict = getattr(management, "ui_layouts", {}) or {}
        payload = ui_layouts.get(layout_id)
        if not isinstance(payload, dict):
            raise RuntimeError(f"未找到 UI 布局: {layout_id}")
        return {"ok": True, "current_package_id": current_package_id, "layout": payload}

    def get_ui_template_payload(self, template_id: str) -> dict:
        current_package_id, _package, management = self._get_current_management_or_raise()
        ui_templates: dict = getattr(management, "ui_widget_templates", {}) or {}
        payload = ui_templates.get(template_id)
        if not isinstance(payload, dict):
            raise RuntimeError(f"未找到 UI 控件模板: {template_id}")
        return {"ok": True, "current_package_id": current_package_id, "template": payload}

    # --------------------------------------------------------------------- ui sources (html)
    def get_ui_source_catalog_payload(self) -> dict:
        """返回 UI 源码文件清单（项目存档 + 共享）。"""
        current_package_id, _package, _management = self._get_current_management_or_raise()

        project_root = (
            self._workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / current_package_id
            / "管理配置"
            / "UI源码"
        ).resolve()
        shared_root = (self._workspace_root / "assets" / "资源库" / "共享" / "管理配置" / "UI源码").resolve()

        items: list[dict[str, object]] = []

        def _scan(scope: str, root_dir: Path) -> None:
            if not root_dir.is_dir():
                return
            for p in root_dir.glob("*.htm*"):
                if not p.is_file():
                    continue
                items.append(
                    {
                        "scope": scope,
                        "file_name": p.name,
                        "rel_path": p.name,
                        "is_shared": scope == "shared",
                    }
                )

        _scan("project", project_root)
        _scan("shared", shared_root)

        items.sort(key=lambda it: (0 if it.get("scope") == "project" else 1, str(it.get("file_name", "")).casefold()))

        return {
            "ok": True,
            "current_package_id": current_package_id,
            "project_root": str(project_root),
            "shared_root": str(shared_root),
            "items": items,
        }

    def read_ui_source_payload(self, *, scope: str, rel_path: str) -> dict:
        """读取 UI 源码（scope=project/shared）。"""
        current_package_id, _package, _management = self._get_current_management_or_raise()

        normalized_scope = str(scope or "").strip()
        normalized_rel = str(rel_path or "").strip().replace("\\", "/")
        if not normalized_rel or "/" in normalized_rel or normalized_rel.startswith("."):
            raise RuntimeError(f"非法 UI 源码路径：{normalized_rel!r}（仅允许文件名，不允许子目录）。")
        if not normalized_rel.lower().endswith((".html", ".htm")):
            raise RuntimeError(f"UI 源码仅允许 .html/.htm：{normalized_rel!r}")

        if normalized_scope == "project":
            root_dir = (
                self._workspace_root
                / "assets"
                / "资源库"
                / "项目存档"
                / current_package_id
                / "管理配置"
                / "UI源码"
            ).resolve()
        elif normalized_scope == "shared":
            root_dir = (self._workspace_root / "assets" / "资源库" / "共享" / "管理配置" / "UI源码").resolve()
        else:
            raise RuntimeError(f"scope 非法：{normalized_scope!r}")

        target = (root_dir / normalized_rel).resolve()
        if not target.is_relative_to(root_dir):
            raise RuntimeError(f"非法 UI 源码路径（越界）：{normalized_rel!r}")
        if not target.is_file():
            raise RuntimeError(f"未找到 UI 源码文件：{normalized_rel!r}")

        content = target.read_text(encoding="utf-8")
        return {
            "ok": True,
            "current_package_id": current_package_id,
            "scope": normalized_scope,
            "rel_path": normalized_rel,
            "file_name": target.name,
            "is_shared": normalized_scope == "shared",
            "content": content,
        }

    def save_ui_source_payload(self, *, rel_path: str, content: str) -> dict:
        """保存到项目存档的 UI源码/（共享 UI 源码目录只读）。"""
        current_package_id, _package, _management = self._get_current_management_or_raise()

        normalized_rel = str(rel_path or "").strip().replace("\\", "/")
        if not normalized_rel or "/" in normalized_rel or normalized_rel.startswith("."):
            raise RuntimeError(f"非法 UI 源码路径：{normalized_rel!r}（仅允许文件名，不允许子目录）。")
        if not normalized_rel.lower().endswith((".html", ".htm")):
            raise RuntimeError(f"UI 源码仅允许 .html/.htm：{normalized_rel!r}")

        root_dir = (
            self._workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / current_package_id
            / "管理配置"
            / "UI源码"
        ).resolve()
        root_dir.mkdir(parents=True, exist_ok=True)

        target = (root_dir / normalized_rel).resolve()
        if not target.is_relative_to(root_dir):
            raise RuntimeError(f"非法 UI 源码路径（越界）：{normalized_rel!r}")

        target.write_text(str(content or ""), encoding="utf-8")
        return {
            "ok": True,
            "current_package_id": current_package_id,
            "scope": "project",
            "rel_path": normalized_rel,
            "file_name": target.name,
        }

