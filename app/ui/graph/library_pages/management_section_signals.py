from __future__ import annotations

from .management_sections_base import *


class SignalSection(BaseManagementSection):
    """信号管理 Section（对应 `PackageView.signals` / `GlobalResourceView.signals`）。"""

    section_key = "signals"
    tree_label = "📡 信号管理"
    type_name = "信号"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        signals_dict = self._get_signal_dict_from_package(package)
        if not signals_dict:
            return []

        usage_stats = self._build_signal_usage_stats(package)

        for signal_id, signal_config in signals_dict.items():
            signal_name = signal_config.signal_name or signal_id
            parameter_count = len(signal_config.parameters)

            preview_parameters: list[str] = []
            for parameter_config in signal_config.parameters[:3]:
                if not isinstance(parameter_config, SignalParameterConfig):
                    continue
                parameter_name = parameter_config.name or ""
                parameter_type_name = parameter_config.parameter_type or ""
                if not parameter_name and not parameter_type_name:
                    continue
                if parameter_type_name:
                    preview_parameters.append(f"{parameter_name}({parameter_type_name})")
                else:
                    preview_parameters.append(parameter_name)

            attr1_text = f"参数数量: {parameter_count}"
            attr2_text = ""
            if preview_parameters:
                joined_preview = ", ".join(preview_parameters)
                attr2_text = f"参数预览: {joined_preview}"

            usage_entry = usage_stats.get(signal_id)
            if usage_entry:
                graph_count = int(usage_entry.get("graph_count", 0))
                node_count = int(usage_entry.get("node_count", 0))
                if graph_count > 0 or node_count > 0:
                    usage_text = f"{graph_count} 个图 / {node_count} 个节点中使用"
                else:
                    usage_text = "未在任何服务器节点图中使用"
            else:
                usage_text = "未在任何服务器节点图中使用"
            attr3_text = f"使用情况: {usage_text}"

            yield ManagementRowData(
                name=signal_name,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=signal_config.description or "",
                last_modified="",
                user_data=(self.section_key, signal_id),
            )

    @staticmethod
    def _get_signal_dict_from_package(
        package: ManagementPackage,
    ) -> Dict[str, SignalConfig]:
        raw_signals = getattr(package, "signals", None)
        if not isinstance(raw_signals, dict):
            return {}

        resolved_signals: Dict[str, SignalConfig] = {}
        for signal_id, raw_value in raw_signals.items():
            if not isinstance(signal_id, str) or not signal_id:
                continue
            if isinstance(raw_value, SignalConfig):
                resolved_signals[signal_id] = raw_value
            elif isinstance(raw_value, dict):
                resolved_signals[signal_id] = SignalConfig.deserialize(raw_value)
        return resolved_signals

    @staticmethod
    def _build_signal_usage_stats(
        package: ManagementPackage,
    ) -> Dict[str, Dict[str, int]]:
        """基于当前视图构建 {signal_id: {'graph_count': N, 'node_count': M}} 统计信息。"""
        resource_manager = getattr(package, "resource_manager", None)
        templates = getattr(package, "templates", None)
        instances = getattr(package, "instances", None)
        level_entity = getattr(package, "level_entity", None)
        if resource_manager is None or templates is None or instances is None:
            return {}

        raw_usage: Dict[str, Dict[str, Any]] = {}
        for attachment in iter_all_package_graphs(
            resource_manager,
            templates,
            instances,
            level_entity,
        ):
            graph_config = attachment.graph_config
            if getattr(graph_config, "graph_type", "") != "server":
                continue
            graph_data = graph_config.data or {}
            metadata = graph_data.get("metadata") or {}
            bindings = metadata.get("signal_bindings") or {}
            if not isinstance(bindings, dict):
                continue
            graph_id = attachment.graph_id
            for node_id, binding in bindings.items():
                _ = node_id
                if not isinstance(binding, dict):
                    continue
                signal_id_raw = binding.get("signal_id")
                if not signal_id_raw:
                    continue
                signal_id = str(signal_id_raw)
                entry = raw_usage.setdefault(
                    signal_id,
                    {"node_count": 0, "graph_ids": set()},
                )
                entry["node_count"] = int(entry.get("node_count", 0)) + 1
                graph_ids = entry.get("graph_ids")
                if isinstance(graph_ids, set):
                    graph_ids.add(graph_id)
                else:
                    entry["graph_ids"] = {graph_id}

        if not raw_usage:
            return {}

        result: Dict[str, Dict[str, int]] = {}
        for signal_id, data in raw_usage.items():
            graph_ids = data.get("graph_ids")
            if isinstance(graph_ids, set):
                graph_count = len(graph_ids)
            else:
                graph_count = 0
            node_count = int(data.get("node_count", 0))
            result[signal_id] = {
                "graph_count": graph_count,
                "node_count": node_count,
            }
        return result

    @staticmethod
    def _show_warning(
        parent_widget: QtWidgets.QWidget,
        title: str,
        message: str,
    ) -> None:
        from ui.foundation import dialog_utils

        dialog_utils.show_warning_dialog(parent_widget, title, message)

    def _ensure_unique_signal_name(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        desired_name: str,
        *,
        excluding_signal_id: Optional[str] = None,
    ) -> bool:
        """确保在给定视图下信号名唯一。"""
        normalized_name = desired_name.strip()
        if not normalized_name:
            self._show_warning(parent_widget, "警告", "请输入信号名")
            return False

        signals_dict = self._get_signal_dict_from_package(package)
        for existing_signal_id, existing_config in signals_dict.items():
            if excluding_signal_id and existing_signal_id == excluding_signal_id:
                continue
            if existing_config.signal_name == normalized_name:
                self._show_warning(
                    parent_widget,
                    "警告",
                    f"信号名 '{normalized_name}' 已被其他信号使用，请使用不同的名称。",
                )
                return False
        return True

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        # 信号定义已迁移为代码级常量，管理页面暂不支持直接新建信号。
        _ = (parent_widget, package)
        return False

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        # 信号定义已迁移为代码级常量，管理页面暂不支持直接编辑信号内容。
        _ = (parent_widget, package, item_id)
        return False

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        # 删除信号同样需要在代码层面进行，管理页面仅展示现有定义。
        return False



