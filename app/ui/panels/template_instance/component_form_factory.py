"""通用组件表单工厂。

本模块只做“组件类型 -> 表单实现”的路由与导出；具体表单实现拆分到独立模块，
避免单文件职责过载（巨型面板/巨型表单问题）。
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6 import QtWidgets

from app.ui.panels.template_instance.component_form_backpack import create_backpack_form
from app.ui.panels.template_instance.component_form_nameplate import NameplateConfigForm
from app.ui.panels.template_instance.component_form_tabs import TabConfigForm


def create_component_form(
    component_type: str,
    settings: Dict[str, object],
    parent: QtWidgets.QWidget,
    *,
    on_settings_changed: Optional[Callable[[], None]] = None,
    resource_manager: Optional[object] = None,
    package_index_manager: Optional[object] = None,
) -> QtWidgets.QWidget | None:
    """根据组件类型创建通用组件的配置表单。

    当前仅对少量组件提供简单表单：
    - 背包：背包容量
    - 铭牌：铭牌配置列表（支持多个配置ID与“初始生效”开关）
    - 选项卡：多选项卡配置（序号、排序等级、本地过滤器与本地过滤器节点图 ID）

    其余组件返回 None，由调用方决定展示只读占位说明。
    """
    if component_type == "背包":
        return create_backpack_form(
            settings,
            parent,
            on_settings_changed=on_settings_changed,
        )
    if component_type == "铭牌":
        return NameplateConfigForm(
            settings,
            parent,
            on_settings_changed=on_settings_changed,
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
        )
    if component_type == "选项卡":
        return TabConfigForm(
            settings,
            parent,
            on_settings_changed=on_settings_changed,
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
        )
    return None


__all__ = ["create_component_form"]


