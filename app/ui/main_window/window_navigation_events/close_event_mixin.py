"""窗口关闭与未保存修改提示相关的事件处理 Mixin。"""

from __future__ import annotations

from typing import Any

from PyQt6 import QtGui

from app.ui.foundation import dialog_utils


class CloseEventMixin:
    """统一处理主窗口 closeEvent：未保存提示、清理与增量落盘。"""

    def _build_unsaved_changes_preview_lines(self, *, package_controller: Any) -> list[str]:
        """将 PackageDirtyState 转为用户可读的“未保存修改清单”。

        约定：
        - 仅用于 UI 提示，不参与保存逻辑；
        - 优先展示可读名称，无法解析时回退为 ID/key；
        - 清单行数不做强限制（由弹窗滚动区负责容纳），但会对极端场景做轻量截断提示。
        """
        dirty_snapshot = package_controller.dirty_state.snapshot()
        current_package = package_controller.current_package
        resource_manager = package_controller.resource_manager
        current_package_index = package_controller.current_package_index

        result_lines: list[str] = []

        # ---- 节点图
        if dirty_snapshot.graph_dirty:
            graph_controller = getattr(self, "graph_controller", None)
            current_graph_id = getattr(graph_controller, "current_graph_id", None)
            if isinstance(current_graph_id, str) and current_graph_id:
                graph_display_name = current_graph_id
                graph_metadata = resource_manager.load_graph_metadata(current_graph_id) or {}
                raw_name = graph_metadata.get("name")
                if isinstance(raw_name, str) and raw_name.strip():
                    graph_display_name = raw_name.strip()
                result_lines.append(f"- 节点图：{graph_display_name} ({current_graph_id})")
            else:
                result_lines.append("- 节点图：已修改")

        # ---- 元件
        if dirty_snapshot.template_ids:
            template_getter = getattr(current_package, "get_template", None)
            for template_id in sorted(dirty_snapshot.template_ids, key=lambda text: str(text).casefold()):
                display_text = str(template_id)
                if callable(template_getter):
                    template_obj = template_getter(template_id)
                    if template_obj is not None:
                        template_name = getattr(template_obj, "name", "")
                        if isinstance(template_name, str) and template_name.strip():
                            display_text = f"{template_name.strip()} ({template_id})"
                result_lines.append(f"- 元件：{display_text}")

        # ---- 实体摆放 / 关卡实体
        level_entity_id = getattr(current_package_index, "level_entity_id", None)
        if dirty_snapshot.instance_ids:
            instance_getter = getattr(current_package, "get_instance", None)
            for instance_id in sorted(dirty_snapshot.instance_ids, key=lambda text: str(text).casefold()):
                prefix = "实体摆放"
                if isinstance(level_entity_id, str) and level_entity_id and instance_id == level_entity_id:
                    prefix = "关卡实体"
                display_text = str(instance_id)
                if callable(instance_getter):
                    instance_obj = instance_getter(instance_id)
                    if instance_obj is not None:
                        instance_name = getattr(instance_obj, "name", "")
                        if isinstance(instance_name, str) and instance_name.strip():
                            display_text = f"{instance_name.strip()} ({instance_id})"
                result_lines.append(f"- {prefix}：{display_text}")
        elif dirty_snapshot.level_entity_dirty:
            # 兜底：理论上关卡实体脏时会同时写入 instance_ids，但仍保持清单可读性
            result_lines.append("- 关卡实体：已修改")

        # ---- 战斗预设：索引/引用级修改
        if dirty_snapshot.combat_dirty:
            result_lines.append("- 战斗预设：已修改（索引/引用）")

        # ---- 战斗预设：资源本体修改（按条目粒度）
        if dirty_snapshot.combat_preset_keys:
            from engine.configs.resource_types import ResourceType

            section_to_spec: dict[str, tuple[str, ResourceType]] = {
                "player_template": ("玩家模板", ResourceType.PLAYER_TEMPLATE),
                "player_class": ("职业", ResourceType.PLAYER_CLASS),
                "unit_status": ("单位状态", ResourceType.UNIT_STATUS),
                "skill": ("技能", ResourceType.SKILL),
                "projectile": ("投射物", ResourceType.PROJECTILE),
                "item": ("道具", ResourceType.ITEM),
            }
            preset_keys = sorted(
                dirty_snapshot.combat_preset_keys,
                key=lambda pair: (str(pair[0]).casefold(), str(pair[1]).casefold()),
            )
            for section_key, item_id in preset_keys:
                section_title, resource_type = section_to_spec.get(section_key, (str(section_key), ResourceType.ITEM))
                display_name = str(item_id)
                metadata = resource_manager.get_resource_metadata(resource_type, str(item_id)) or {}
                raw_name = metadata.get("name")
                if isinstance(raw_name, str) and raw_name.strip():
                    display_name = raw_name.strip()
                result_lines.append(f"- 战斗预设/{section_title}：{display_name} ({item_id})")

        # ---- 管理配置
        if dirty_snapshot.full_management_sync:
            result_lines.append("- 管理配置：需要全量同步")
        elif dirty_snapshot.management_keys:
            from app.ui.management.section_registry import MANAGEMENT_SECTIONS

            section_key_to_title = {spec.key: spec.title for spec in MANAGEMENT_SECTIONS}
            for section_key in sorted(dirty_snapshot.management_keys, key=lambda text: str(text).casefold()):
                title = section_key_to_title.get(section_key, str(section_key))
                result_lines.append(f"- 管理配置：{title}")

        # ---- 信号与索引
        if dirty_snapshot.signals_dirty:
            result_lines.append("- 信号引用：已修改")
        if dirty_snapshot.index_dirty:
            result_lines.append("- 项目存档索引：已修改")

        # ---- 极端兜底与截断提示
        if not result_lines:
            result_lines.append("- 未能解析具体修改清单（建议选择“保存并退出”以避免丢失修改）")

        max_lines = 200
        if len(result_lines) > max_lines:
            hidden_count = len(result_lines) - max_lines
            result_lines = result_lines[:max_lines]
            result_lines.append(f"- ... 以及更多 {hidden_count} 项（已省略）")

        return result_lines

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """窗口关闭事件。

        重要：关闭时不要无条件执行“全量保存”。

        背景：
        - 资源库支持外部工具修改 + 自动刷新到 UI；
        - 若关闭时强制走 `save_package()`（force_full=True），会把当前属性面板/内存视图中的对象
          无条件序列化写回资源文件与索引，进而出现“外部更新已刷新到 UI，但退出又被旧内容覆盖”的问题。

        策略：
        - 先保存 UI 会话状态；
        - 清理 FileWatcher，避免关闭阶段的内部写盘触发刷新/重载；
        - 显式 flush 基础信息页的去抖改动（若存在），让 dirty_state 能准确反映真实本地改动；
        - 最后按脏块增量落盘：dirty_state 为空则不写盘，避免无意义覆盖。
        """
        package_controller = getattr(self, "package_controller", None)

        has_unsaved_changes = False
        if package_controller is not None:
            has_unsaved_method = getattr(package_controller, "has_unsaved_changes", None)
            if callable(has_unsaved_method):
                has_unsaved_changes = bool(has_unsaved_method())
            else:
                dirty_state = getattr(package_controller, "dirty_state", None)
                is_empty_method = getattr(dirty_state, "is_empty", None)
                if callable(is_empty_method):
                    has_unsaved_changes = not bool(is_empty_method())

        should_save_before_exit = True
        if has_unsaved_changes:
            current_package_name = ""
            if package_controller is not None:
                current_package = getattr(package_controller, "current_package", None)
                name_value = getattr(current_package, "name", "")
                current_package_name = str(name_value or "")
            package_name_line = (
                f"当前项目存档：{current_package_name}" if current_package_name else "当前项目存档：<未命名>"
            )
            unsaved_preview_lines: list[str] = []
            if package_controller is not None:
                unsaved_preview_lines = self._build_unsaved_changes_preview_lines(
                    package_controller=package_controller
                )

            choice = dialog_utils.ask_choice_dialog(
                self,
                "退出前保存",
                "检测到未保存的修改：\n" f"{package_name_line}\n\n" "请选择要执行的操作：",
                icon="question",
                choices=[
                    ("save", "保存并退出", "accept"),
                    ("discard", "不保存退出", "destructive"),
                    ("cancel", "取消", "reject"),
                ],
                default_choice_key="save",
                escape_choice_key="cancel",
                details_title="已修改内容（未保存）",
                details_lines=unsaved_preview_lines,
            )
            if choice == "cancel":
                event.ignore()
                return
            if choice == "discard":
                should_save_before_exit = False
                if package_controller is not None:
                    package_controller.reset_dirty_state()
                self._set_last_save_status("saved")

        self._save_ui_session_state()

        # 退出阶段必须先停掉可能跨线程 emit Qt 信号的异步加载与线程池，
        # 避免窗口销毁过程中出现 native access violation。
        from app.ui.panels.graph_async_loader import shutdown_graph_async_loader_system
        from app.runtime.services.graph_data_service import shutdown_graph_resource_load_executor

        shutdown_graph_async_loader_system()
        shutdown_graph_resource_load_executor()
        refresh_coordinator = getattr(self, "_resource_refresh_coordinator", None)
        if refresh_coordinator is not None:
            refresh_coordinator.cleanup()
        self.file_watcher_manager.cleanup()

        if package_controller is not None and should_save_before_exit:
            self._set_last_save_status("saving")
            flush_callback = getattr(package_controller, "flush_current_resource_panel", None)
            if callable(flush_callback):
                flush_callback()

            if hasattr(package_controller, "save_dirty_blocks"):
                package_controller.save_dirty_blocks()
            else:
                package_controller.save_package()
            self._set_last_save_status("saved")

        from engine.configs.settings import settings

        settings.save()
        event.accept()


