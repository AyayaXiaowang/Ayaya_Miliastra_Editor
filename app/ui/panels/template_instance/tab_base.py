"""Shared base for context-aware template/instance tabs."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Sequence, Tuple, Union

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from ui.panels.template_instance_service import TemplateInstanceService


PackageType = Union[PackageView, GlobalResourceView]
ConfigType = Union[TemplateConfig, InstanceConfig]


def is_drop_template_config(template: Optional[TemplateConfig]) -> bool:
    """判定给定模板是否为“掉落物”类别。

    判定规则：
    - metadata.template_category == "掉落物"
    - 或 metadata.is_drop_item 为 True
    """
    if not isinstance(template, TemplateConfig):
        return False
    metadata = getattr(template, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return False
    if metadata.get("template_category") == "掉落物":
        return True
    if metadata.get("is_drop_item") is True:
        return True
    return False


class TemplateInstanceTabBase(QtWidgets.QWidget):
    """统一管理上下文、清理与工具栏构建的标签页基类。"""

    data_changed = QtCore.pyqtSignal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.current_object: Optional[ConfigType] = None
        self.current_package: Optional[PackageType] = None
        self.object_type: str = ""
        self.service: Optional[TemplateInstanceService] = None
        self.resource_manager: Optional[Any] = None
        self.package_index_manager: Optional[Any] = None

    # 公共上下文管理 ------------------------------------------------------
    def clear(self) -> None:
        self.current_object = None
        self.current_package = None
        self.object_type = ""
        self._reset_ui()

    def set_context(
        self,
        current_object: Optional[ConfigType],
        object_type: str,
        package: Optional[PackageType],
        *,
        force: bool = False,
    ) -> None:
        if not current_object:
            self._reset_ui()
            return
        if (
            not force
            and current_object is self.current_object
            and object_type == self.object_type
            and package is self.current_package
        ):
            return
        self.current_object = current_object
        self.object_type = object_type
        self.current_package = package
        self._refresh_ui()

    # 子类需实现的钩子 ----------------------------------------------------
    def _reset_ui(self) -> None:
        """子类负责清空自身控件。"""
        raise NotImplementedError

    def _refresh_ui(self) -> None:
        """子类负责根据 current_object 刷新控件。"""
        raise NotImplementedError

    # 工具栏辅助 ----------------------------------------------------------
    def _build_toolbar(self, specs: Sequence[Tuple[str, Callable[[], None]]]) -> QtWidgets.QHBoxLayout:
        layout = QtWidgets.QHBoxLayout()
        for text, handler in specs:
            button = QtWidgets.QPushButton(text, self)
            button.clicked.connect(handler)
            layout.addWidget(button)
        layout.addStretch()
        return layout

    def _init_panel_layout(
        self,
        specs: Sequence[Tuple[str, Callable[[], None]]],
    ) -> QtWidgets.QVBoxLayout:
        """构造“工具栏 + 内容”常规布局，减少子类样板代码。"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(self._build_toolbar(specs))
        return layout

    # 依赖注入 ------------------------------------------------------------
    def set_service(self, service: TemplateInstanceService) -> None:
        self.service = service

    def set_resource_manager(self, resource_manager) -> None:
        self.resource_manager = resource_manager

    def set_package_index_manager(self, manager) -> None:
        self.package_index_manager = manager

    # 数据辅助 ------------------------------------------------------------
    def _collect_context_lists(
        self,
        *,
        template_attr: str,
        instance_attr: str,
        level_attr: str,
    ) -> tuple[list[Any], list[Any], list[Any]]:
        template_items: list[Any] = []
        instance_items: list[Any] = []
        level_items: list[Any] = []
        if not self.current_object:
            return template_items, instance_items, level_items
        if self.object_type == "template":
            template_items = list(getattr(self.current_object, template_attr, []))
            return template_items, instance_items, level_items
        if self.object_type == "level_entity":
            level_items = list(getattr(self.current_object, level_attr, []))
            return template_items, instance_items, level_items
        if self.object_type == "instance":
            instance_obj = self._current_instance()
            if instance_obj:
                instance_items = list(getattr(instance_obj, instance_attr, []))
                template_obj = self._template_for_instance(instance_obj)
                if template_obj:
                    template_items = list(getattr(template_obj, template_attr, []))
        return template_items, instance_items, level_items

    def _current_instance(self) -> Optional[InstanceConfig]:
        if isinstance(self.current_object, InstanceConfig):
            return self.current_object
        return None

    def _template_for_instance(self, instance_obj: InstanceConfig) -> Optional[TemplateConfig]:
        if not self.current_package:
            return None
        return self.current_package.get_template(instance_obj.template_id)

    # 掉落物上下文辅助 -------------------------------------------------------
    def _is_drop_item_context(self) -> bool:
        """当前上下文是否为“掉落物”模板或其实例。

        判定规则与 is_drop_template_config 一致：
        - 模板：metadata.template_category == "掉落物" 或 is_drop_item 为 True
        - 实例：其模板满足上述条件
        """
        if not self.current_object:
            return False

        if self.object_type == "template" and isinstance(self.current_object, TemplateConfig):
            return is_drop_template_config(self.current_object)

        if self.object_type == "instance":
            instance_obj = self._current_instance()
            if not instance_obj:
                return False
            template_obj = self._template_for_instance(instance_obj)
            return is_drop_template_config(template_obj)

        return False

    # 只读模式 --------------------------------------------------------------
    def set_read_only(self, read_only: bool) -> None:  # pragma: no cover - 默认空实现供子类覆写
        """可选：由子类实现的只读状态切换钩子。

        默认不做任何处理，具体标签页在需要时自行覆盖该方法，按需禁用/启用内部编辑控件。
        """
        return

