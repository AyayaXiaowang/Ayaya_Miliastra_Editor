from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.package_model import ComponentConfig, InstanceConfig, TemplateConfig
from app.ui.panels.template_instance.components_tab import ComponentsTab
from app.ui.panels.template_instance_service import TemplateInstanceService


_app = QtWidgets.QApplication.instance()
if _app is None:
    _app = QtWidgets.QApplication([])


def _wait_ms(ms: int) -> None:
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_components_tab_renders_component_cards_smoke() -> None:
    tab = ComponentsTab()
    tab.set_service(TemplateInstanceService())

    template = TemplateConfig(
        template_id="tpl_1",
        name="DemoTemplate",
        entity_type="造物",
        default_components=[
            ComponentConfig(component_type="背包", settings={"背包容量": 30}),
            ComponentConfig(component_type="铭牌", settings={"铭牌配置列表": []}),
        ],
    )

    tab.set_context(template, "template", package=None, force=True)

    cards = tab.findChildren(QtWidgets.QFrame, "ComponentCard")
    assert len(cards) == 2


def test_components_tab_backpack_form_change_emits_data_changed_and_updates_settings() -> None:
    tab = ComponentsTab()
    tab.set_service(TemplateInstanceService())

    template = TemplateConfig(
        template_id="tpl_1",
        name="DemoTemplate",
        entity_type="造物",
        default_components=[
            ComponentConfig(component_type="背包", settings={"背包容量": 20}),
        ],
    )
    tab.set_context(template, "template", package=None, force=True)

    emitted: list[int] = []
    tab.data_changed.connect(lambda: emitted.append(1))

    # 仅一个组件，SpinBox 即背包容量
    spin = tab.findChild(QtWidgets.QSpinBox)
    assert spin is not None
    spin.setValue(spin.value() + 1)

    # ComponentsTab 内部对设置变更做了 debounce，等待 timer 触发
    _wait_ms(260)
    assert emitted, "修改背包容量后应触发 data_changed（用于去抖落盘链路）"
    assert template.default_components[0].settings.get("背包容量") == spin.value()


def test_components_tab_inherited_component_is_readonly_in_instance_context() -> None:
    tab = ComponentsTab()
    tab.set_service(TemplateInstanceService())

    template = TemplateConfig(
        template_id="tpl_1",
        name="DemoTemplate",
        entity_type="造物",
        default_components=[
            ComponentConfig(component_type="背包", settings={"背包容量": 20}),
        ],
    )
    instance = InstanceConfig(
        instance_id="ins_1",
        name="DemoInstance",
        template_id="tpl_1",
    )

    class _DummyPackage:
        def get_template(self, template_id: str):
            return template if template_id == template.template_id else None

    tab.set_context(instance, "instance", package=_DummyPackage(), force=True)

    spin = tab.findChild(QtWidgets.QSpinBox)
    assert spin is not None
    assert not spin.isEnabled(), "实体上下文中的继承组件应为只读（禁用编辑控件）"


