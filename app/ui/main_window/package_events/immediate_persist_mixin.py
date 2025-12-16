"""库页数据变更→脏标记→去抖落盘请求。"""

from __future__ import annotations

from PyQt6 import QtCore

from app.models.view_modes import ViewMode
from app.ui.graph.library_pages.library_scaffold import LibraryChangeEvent


class ImmediatePersistMixin:
    """统一处理各种库页/面板发出的“需要立即持久化”的请求。"""

    def _on_library_page_data_changed(self, event: LibraryChangeEvent) -> None:
        """统一处理库/列表页发出的 LibraryChangeEvent。

        当前实现仅关心“有真实数据变更”这一事实，具体的变更内容与范围
        仍由各库页自身与控制器协同处理；后续如需按资源类型做差异化处理，
        可在此方法中根据 event.kind / event.operation / event.context 分派逻辑。
        """
        template_id: str | None = None
        instance_id: str | None = None
        management_keys: set[str] | None = None
        combat_dirty = False
        signals_dirty = False
        graph_dirty = False
        index_dirty = False

        kind = getattr(event, "kind", "") or ""
        operation = getattr(event, "operation", "") or ""
        context = getattr(event, "context", None)

        if kind == "template":
            template_id = event.id
        elif kind == "instance":
            instance_id = event.id
        elif kind == "graph":
            graph_dirty = True
        elif kind == "combat":
            combat_dirty = True
            index_dirty = True
        elif kind == "management":
            combat_dirty = False
            section_key = None
            if isinstance(context, dict):
                section_key = context.get("section_key")
            if isinstance(section_key, str) and section_key:
                management_keys = {section_key}
            index_dirty = True
        elif kind == "signal":
            signals_dirty = True
            index_dirty = True

        if operation in {"create", "delete"}:
            index_dirty = True

        self._on_immediate_persist_requested(
            graph_dirty=graph_dirty,
            template_id=template_id,
            instance_id=instance_id,
            management_keys=management_keys,
            combat_dirty=combat_dirty,
            signals_dirty=signals_dirty,
            index_dirty=index_dirty,
        )

    def _on_data_updated(self) -> None:
        """右侧属性面板的数据更新"""
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())

        # 模板/实例/关卡实体属性面板共用同一条“数据更新”链路，但不同模式下的
        # 刷新需求并不相同：
        # - 在元件库或其它以模板为主的视图中，仍需要刷新元件列表以反映名称/描述等改动；
        # - 在实体摆放视图中，编辑的是实体实例（object_type == "instance"）时，
        #   不应触发元件库的选中事件去抢占右侧属性上下文，否则会出现
        #   “修改实体 GUID → 右侧突然切回某个元件属性”的错觉。
        if current_view_mode != ViewMode.PLACEMENT:
            # 非实体摆放模式下，保持原有行为：始终刷新元件库列表。
            self.template_widget.refresh_templates()
        else:
            # 实体摆放模式中，仅当当前属性面板上下文不是实体实例时，才刷新元件库。
            # 例如：通过任务清单或节点图库在此模式下只读查看某个元件。
            if getattr(self.property_panel, "object_type", "") != "instance":
                self.template_widget.refresh_templates()

        if (
            current_view_mode == ViewMode.PLACEMENT
            and getattr(self.property_panel, "object_type", "") == "instance"
        ):
            self.placement_widget.refresh_instances()

        # 右侧属性面板的任何改动都应立即持久化到资源库与存档索引，
        # 避免仅停留在 UI 模型或内存视图中。
        obj = getattr(self.property_panel, "current_object", None)
        object_type = getattr(self.property_panel, "object_type", None)
        template_id: str | None = None
        instance_id: str | None = None
        if object_type == "template" and hasattr(obj, "template_id"):
            template_id = getattr(obj, "template_id")
        elif object_type in ("instance", "level_entity") and hasattr(obj, "instance_id"):
            instance_id = getattr(obj, "instance_id")
        self._on_immediate_persist_requested(
            template_id=template_id,
            instance_id=instance_id,
        )

    def _on_immediate_persist_requested(
        self,
        *,
        graph_dirty: bool = False,
        template_id: str | None = None,
        instance_id: str | None = None,
        management_keys: set[str] | None = None,
        combat_dirty: bool = False,
        signals_dirty: bool = False,
        index_dirty: bool = False,
    ) -> None:
        """要求立即将当前存档的增删改写入本地资源与索引（按脏块增量落盘）。

        为避免在短时间内因多次属性变更触发频繁落盘，这里使用单次定时器做轻量去抖：
        在最近一次请求后的短暂间隔内合并为一次实际保存。
        """
        if not hasattr(self, "package_controller"):
            return

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if not current_package_id:
            return

        controller = getattr(self, "package_controller")
        if controller is not None:
            if graph_dirty:
                controller.mark_graph_dirty()
            if template_id:
                controller.mark_template_dirty(template_id)
            if instance_id:
                controller.mark_instance_dirty(instance_id)
            if management_keys:
                controller.mark_management_dirty(management_keys)
            if combat_dirty:
                controller.mark_combat_dirty()
            if signals_dirty:
                controller.mark_signals_dirty()
            if index_dirty:
                controller.mark_index_dirty()

        # 懒初始化去抖定时器
        timer = getattr(self, "_immediate_persist_timer", None)
        if timer is None or not isinstance(timer, QtCore.QTimer):
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)

            def _do_persist() -> None:
                # 定时器触发时再次确认仍存在有效存档ID
                controller = getattr(self, "package_controller", None)
                if controller is None:
                    return
                package_id = getattr(controller, "current_package_id", None)
                if not package_id:
                    return
                if hasattr(controller, "save_dirty_blocks"):
                    controller.save_dirty_blocks()
                else:
                    controller.save_package()

            timer.timeout.connect(_do_persist)
            setattr(self, "_immediate_persist_timer", timer)

        # 短暂合并多次请求（例如快速编辑/识别联动等场景）
        # 200ms 通常足以合并一批连续 UI 事件，又不会让用户感觉到明显延迟。
        timer.start(200)


