from __future__ import annotations

from datetime import datetime

from engine.configs.resource_types import ResourceType

from .bridge_base import _ImportBundleResult, _ImportResult


class _UiWorkbenchBridgeImportLayoutsMixin:
    def import_layout_from_template_payload(self, *, layout_name: str, template_payload: dict) -> _ImportResult:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再执行导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法导入")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法导入")

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            raise RuntimeError("package_controller 缺少 resource_manager，无法导入")

        # 写入当前包的 management 缓存（后续由 ManagementSaveService 统一落盘并同步索引）
        if not isinstance(getattr(management, "ui_widget_templates", None), dict):
            management.ui_widget_templates = {}
        if not isinstance(getattr(management, "ui_layouts", None), dict):
            management.ui_layouts = {}

        # --- 生成新 ID（全库同类型唯一）
        existing_layout_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_LAYOUT).keys())
        existing_template_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_WIDGET_TEMPLATE).keys())

        layout_id = self._generate_unique_id(prefix="layout_html", existing=existing_layout_ids)
        template_id = self._generate_unique_id(prefix="ui_widget_template_html", existing=existing_template_ids)

        # --- 规范化名称（避免 UI 列表中同名混淆）
        normalized_layout_name = self._ensure_unique_name(
            desired=str(layout_name or "").strip() or "HTML导入_界面布局",
            existing_names=self._collect_existing_names(getattr(management, "ui_layouts", None), "layout_name"),
        )
        normalized_template_name = self._ensure_unique_name(
            desired=f"{normalized_layout_name}（HTML组合）",
            existing_names=self._collect_existing_names(getattr(management, "ui_widget_templates", None), "template_name"),
        )

        now = datetime.now().isoformat()

        # --- 解析 Workbench 导出的 UIControlGroupTemplate，并重写 ID/名称/控件ID（避免跨模板 widget_id 冲突）
        from engine.configs.components.ui_control_group_model import (
            BUILTIN_WIDGET_TYPES,
            UIControlGroupTemplate,
            UIWidgetConfig,
            UILayout,
            create_builtin_widget_templates,
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

        # --- 固有内容：优先使用“按包后缀化”的 builtin 模板（与资源库内约定一致）
        existing_ui_templates: dict = management.ui_widget_templates
        builtin_base_templates = create_builtin_widget_templates()

        builtin_widgets: list[str] = []
        for widget_type in list(BUILTIN_WIDGET_TYPES):
            preferred_template_id = f"builtin_{widget_type}__{current_package_id}"
            legacy_template_id = f"builtin_{widget_type}"

            if preferred_template_id in existing_ui_templates:
                builtin_widgets.append(preferred_template_id)
                continue
            if legacy_template_id in existing_ui_templates:
                builtin_widgets.append(legacy_template_id)
                continue

            # 缺失时补齐：用引擎内建默认位置/大小作为兜底，并将 ID 后缀化为 __<package_id>
            base_template = builtin_base_templates.get(legacy_template_id)
            if base_template is None:
                continue

            payload = base_template.serialize()
            payload["template_id"] = preferred_template_id
            payload["template_name"] = widget_type
            payload["created_at"] = now
            payload["updated_at"] = now

            widgets_payload = payload.get("widgets")
            if isinstance(widgets_payload, list):
                for widget_payload_item in widgets_payload:
                    if not isinstance(widget_payload_item, dict):
                        continue
                    widget_payload_item["widget_id"] = f"builtin_{widget_type}_widget__{current_package_id}"
                    widget_payload_item["widget_type"] = widget_type
                    widget_payload_item["widget_name"] = widget_type
                    widget_payload_item["is_builtin"] = True

            existing_ui_templates[preferred_template_id] = payload
            builtin_widgets.append(preferred_template_id)

        # --- 写入组合模板（用于溯源/整体预览），但布局默认引用“拆分后的单控件模板”
        existing_ui_templates[template_id] = template_obj.serialize()

        # --- 拆分导入（增强）：优先将“按钮”打组为组合模板（一个按钮 = 多控件组合），其余仍按单控件拆分。
        #
        # 设计动机：
        # - HTML 中一个 <button> 往往只需样式即可表达；
        # - 但在 UGC UI 中按钮通常由“文本框 + 进度条底色 + 进度条阴影 + 交互层(道具展示)”堆叠实现；
        # - 若完全按控件拆分，布局自定义列表会非常长且难以维护。
        #
        # 约定（与现有导出一致）：
        # - Workbench 会为每个 <button> 生成一个“道具展示”控件（交互层）；
        # - 并为其底色/阴影/边框生成若干“进度条”，文本生成“文本框”。
        existing_template_names = self._collect_existing_names(existing_ui_templates, "template_name")
        custom_group_entries: list[tuple[int, str]] = []  # (sort_key(min_layer_index), template_id)

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

        # 以 layer_index 升序稳定排序（背景→前景），避免导入后列表顺序随机
        source_widgets = sorted(
            list(template_obj.widgets),
            key=lambda w: int(getattr(w, "layer_index", 0) or 0),
        )

        # 1) “按钮打组”：以 <button> 导出的交互层（道具展示）作为锚点，将其底色/阴影/边框/文本聚合成一个组合模板。
        button_anchors = [
            w
            for w in source_widgets
            if (str(getattr(w, "widget_type", "") or "") == "道具展示") and (not bool(getattr(w, "is_builtin", False)))
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

            desired_template_id_prefix = f"{template_id}_btn"
            new_template_id = self._generate_unique_id(prefix=desired_template_id_prefix, existing=existing_template_ids)
            existing_template_ids.add(new_template_id)

            # 模板名：尽量使用 aria-label / data-debug-label；否则回退 widget_name
            debug_label = ""
            if isinstance(getattr(anchor, "extra", None), dict):
                debug_label = str(
                    anchor.extra.get("_html_data_debug_label")
                    or anchor.extra.get("_html_button_aria_label")
                    or ""
                ).strip()
            fallback_name = str(getattr(anchor, "widget_name", "") or "").strip()
            label_text = debug_label or fallback_name or f"按钮_{button_index:03d}"
            if label_text.startswith("按钮_道具展示_"):
                label_text = label_text[len("按钮_道具展示_") :]
            desired_template_name = f"{normalized_layout_name}_按钮_{label_text}" if label_text else f"{normalized_layout_name}_按钮_{button_index:03d}"
            normalized_child_name = self._ensure_unique_name(desired=desired_template_name, existing_names=existing_template_names)
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
            existing_ui_templates[new_template_id] = child_template.serialize()
            min_layer = min(int(getattr(w, "layer_index", 0) or 0) for w in members_sorted) if members_sorted else 0
            custom_group_entries.append((min_layer, new_template_id))

        # 2) 其余控件：保持“单控件模板”语义，便于在布局详情中逐项查看与调整
        for widget_index, source_widget in enumerate(source_widgets):
            if source_widget.widget_id in widgets_in_button_groups:
                continue
            desired_template_id_prefix = f"{template_id}_part"
            new_template_id = self._generate_unique_id(prefix=desired_template_id_prefix, existing=existing_template_ids)
            existing_template_ids.add(new_template_id)

            widget_obj = _clone_widget_with_new_id(source_widget, new_widget_id=f"{new_template_id}_w000")
            base_name = str(getattr(widget_obj, "widget_name", "") or "").strip() or str(getattr(widget_obj, "widget_type", "") or "").strip()
            desired_template_name = f"{normalized_layout_name}_{base_name}" if base_name else f"{normalized_layout_name}_控件_{widget_index:03d}"
            normalized_child_name = self._ensure_unique_name(desired=desired_template_name, existing_names=existing_template_names)
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
            existing_ui_templates[new_template_id] = child_template.serialize()
            custom_group_entries.append((int(getattr(widget_obj, "layer_index", 0) or 0), new_template_id))

        # 稳定排序：背景→前景
        custom_group_entries.sort(key=lambda pair: (pair[0], pair[1]))
        custom_group_template_ids = [template_id for _layer, template_id in custom_group_entries]

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
        management.ui_layouts[layout_id] = layout_obj.serialize()

        # 触发增量落盘：只同步 ui_layouts + ui_widget_templates
        mark_management_dirty = getattr(package_controller, "mark_management_dirty", None)
        if callable(mark_management_dirty):
            mark_management_dirty({"ui_layouts", "ui_widget_templates"})
        mark_index_dirty = getattr(package_controller, "mark_index_dirty", None)
        if callable(mark_index_dirty):
            mark_index_dirty()

        save_dirty_blocks = getattr(package_controller, "save_dirty_blocks", None)
        if callable(save_dirty_blocks):
            save_dirty_blocks()

        # UI 刷新：尽力刷新管理页的 UIControlGroupManager
        self._refresh_ui_control_group_manager(package=package)

        return _ImportResult(
            layout_id=layout_id,
            layout_name=normalized_layout_name,
            template_id=template_id,
            template_name=normalized_template_name,
            template_count=len(custom_group_template_ids),
            widget_count=len(template_obj.widgets),
        )

    def import_layout_from_bundle_payload(self, *, layout_name: str, bundle_payload: dict) -> _ImportBundleResult:
        """导入 Workbench 导出的 bundle（UILayout + 多个 UIControlGroupTemplate）。

        约定：
        - Web 侧负责“HTML → 扁平层 → widgets → 打组 → bundle”；
        - Python 侧负责：生成全库唯一 ID、写入 management、触发增量落盘与 UI 刷新。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再执行导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法导入")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法导入")

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            raise RuntimeError("package_controller 缺少 resource_manager，无法导入")

        # 写入当前包的 management 缓存（后续由 ManagementSaveService 统一落盘并同步索引）
        if not isinstance(getattr(management, "ui_widget_templates", None), dict):
            management.ui_widget_templates = {}
        if not isinstance(getattr(management, "ui_layouts", None), dict):
            management.ui_layouts = {}

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

        # --- 生成新 ID（全库同类型唯一）
        existing_layout_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_LAYOUT).keys())
        existing_template_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_WIDGET_TEMPLATE).keys())
        layout_id = self._generate_unique_id(prefix="layout_html", existing=existing_layout_ids)

        now = datetime.now().isoformat()

        # --- 规范化名称（避免 UI 列表中同名混淆）
        desired_layout_name = str(layout_name or "").strip()
        if not desired_layout_name:
            desired_layout_name = str(bundle_layout.get("layout_name", "") or bundle_layout.get("name", "") or "").strip()
        if not desired_layout_name:
            desired_layout_name = "HTML导入_界面布局"
        normalized_layout_name = self._ensure_unique_name(
            desired=desired_layout_name,
            existing_names=self._collect_existing_names(getattr(management, "ui_layouts", None), "layout_name"),
        )

        from engine.configs.components.ui_control_group_model import (
            BUILTIN_WIDGET_TYPES,
            UIControlGroupTemplate,
            UILayout,
            create_builtin_widget_templates,
        )

        existing_ui_templates: dict = management.ui_widget_templates

        # --- 固有内容：优先使用“按包后缀化”的 builtin 模板（与资源库内约定一致）
        builtin_base_templates = create_builtin_widget_templates()
        builtin_widgets: list[str] = []
        for widget_type in list(BUILTIN_WIDGET_TYPES):
            preferred_template_id = f"builtin_{widget_type}__{current_package_id}"
            legacy_template_id = f"builtin_{widget_type}"

            if preferred_template_id in existing_ui_templates:
                builtin_widgets.append(preferred_template_id)
                continue
            if legacy_template_id in existing_ui_templates:
                builtin_widgets.append(legacy_template_id)
                continue

            base_template = builtin_base_templates.get(legacy_template_id)
            if base_template is None:
                continue

            payload = base_template.serialize()
            payload["template_id"] = preferred_template_id
            payload["template_name"] = widget_type
            payload["created_at"] = now
            payload["updated_at"] = now

            widgets_payload = payload.get("widgets")
            if isinstance(widgets_payload, list):
                for widget_payload_item in widgets_payload:
                    if not isinstance(widget_payload_item, dict):
                        continue
                    widget_payload_item["widget_id"] = f"builtin_{widget_type}_widget__{current_package_id}"
                    widget_payload_item["widget_type"] = widget_type
                    widget_payload_item["widget_name"] = widget_type
                    widget_payload_item["is_builtin"] = True

            existing_ui_templates[preferred_template_id] = payload
            builtin_widgets.append(preferred_template_id)

        existing_template_names = self._collect_existing_names(existing_ui_templates, "template_name")
        template_id_map: dict[str, str] = {}
        imported_widget_count = 0

        # --- 写入 bundle templates
        for raw_template_payload in templates_payload_list:
            template_obj = UIControlGroupTemplate.deserialize(raw_template_payload)
            if template_obj is None:
                raise RuntimeError("导入失败：bundle.templates 内存在缺少 template_id 的条目。")

            old_template_id = str(getattr(template_obj, "template_id", "") or "")
            new_template_id = self._generate_unique_id(prefix="ui_widget_template_html", existing=existing_template_ids)
            existing_template_ids.add(new_template_id)

            template_obj.template_id = new_template_id

            desired_template_name = str(getattr(template_obj, "template_name", "") or "").strip() or old_template_id or new_template_id
            normalized_template_name = self._ensure_unique_name(desired=desired_template_name, existing_names=existing_template_names)
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
            existing_ui_templates[new_template_id] = template_obj.serialize()
            if old_template_id:
                template_id_map[old_template_id] = new_template_id

        # --- 生成 layout.custom_groups（优先用 bundle 的顺序）
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

        # --- UI 多状态：导入 layout.visibility_overrides
        # 说明：
        # - Web 侧导出的 bundle.layout.visibility_overrides 的 key 为“旧 template_id”；
        # - Python 导入时会重写 template_id，因此这里必须按 template_id_map 映射到“新 template_id”。
        raw_visibility_overrides = bundle_layout.get("visibility_overrides", {})
        visibility_overrides: dict[str, bool] = {}
        if isinstance(raw_visibility_overrides, dict):
            for old_template_id_value, visible_value in raw_visibility_overrides.items():
                old_template_id = str(old_template_id_value or "").strip()
                if not old_template_id:
                    continue
                new_template_id = template_id_map.get(old_template_id)
                if not new_template_id:
                    continue
                visibility_overrides[new_template_id] = bool(visible_value)

        layout_obj = UILayout(
            layout_id=layout_id,
            layout_name=normalized_layout_name,
            builtin_widgets=builtin_widgets,
            custom_groups=custom_groups,
            default_for_player=default_for_player,
            description=description,
            created_at=now,
            updated_at=now,
            visibility_overrides=visibility_overrides,
        )
        management.ui_layouts[layout_id] = layout_obj.serialize()

        # 触发增量落盘：只同步 ui_layouts + ui_widget_templates
        mark_management_dirty = getattr(package_controller, "mark_management_dirty", None)
        if callable(mark_management_dirty):
            mark_management_dirty({"ui_layouts", "ui_widget_templates"})
        mark_index_dirty = getattr(package_controller, "mark_index_dirty", None)
        if callable(mark_index_dirty):
            mark_index_dirty()

        save_dirty_blocks = getattr(package_controller, "save_dirty_blocks", None)
        if callable(save_dirty_blocks):
            save_dirty_blocks()

        # UI 刷新：尽力刷新管理页的 UIControlGroupManager
        self._refresh_ui_control_group_manager(package=package)

        return _ImportBundleResult(
            layout_id=layout_id,
            layout_name=normalized_layout_name,
            template_count=len(template_id_map),
            widget_count=imported_widget_count,
        )

