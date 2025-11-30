"""Template/instance property panel composed of modular tab widgets."""

from __future__ import annotations

from typing import Callable, Optional, Union, cast

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from ui.foundation.theme_manager import Colors, Sizes
from ui.panels.graph_data_provider import GraphDataProvider, get_shared_graph_data_provider
from ui.panels.package_membership_selector import build_package_membership_row
from ui.panels.panel_scaffold import PanelScaffold
from ui.panels.template_instance.basic_info_tab import BasicInfoTab
from ui.panels.template_instance.components_tab import ComponentsTab
from ui.panels.template_instance.graphs_tab import GraphsTab
from ui.panels.template_instance.variables_tab import VariablesTab
from ui.panels.template_instance.tab_base import TemplateInstanceTabBase, is_drop_template_config
from ui.panels.template_instance_service import TemplateInstanceService


class TemplateInstancePanel(PanelScaffold):
    """统一的元件属性面板，负责装配标签页与信号转发。"""

    data_updated = QtCore.pyqtSignal()
    graph_selected = QtCore.pyqtSignal(str, dict)
    # 模板所属存档变更 (template_id, package_id, is_checked)
    template_package_membership_changed = QtCore.pyqtSignal(str, str, bool)
    # 实例所属存档变更 (instance_id, package_id, is_checked)
    instance_package_membership_changed = QtCore.pyqtSignal(str, str, bool)

    def __init__(
        self,
        resource_manager: Optional[ResourceManager] = None,
        package_index_manager: Optional[PackageIndexManager] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(
            parent,
            title="属性",
            description="查看并编辑元件、实体与关卡实体的基础信息、通用组件与变量。",
        )
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        self.current_package: Optional[Union[PackageView, GlobalResourceView]] = None
        self.current_object: Optional[Union[TemplateConfig, InstanceConfig]] = None
        self.object_type: str = ""
        self.service = TemplateInstanceService()
        self.graph_data_provider = get_shared_graph_data_provider(resource_manager, package_index_manager)
        # 只读模式开关：
        # - 在模板/实例页面中保持可编辑（False）
        # - 在任务清单等只读上下文中由上层切换为 True，禁用内部编辑控件但保留标签切换能力
        self._read_only: bool = False
        self._pending_tab_contexts: dict[
            int,
            tuple[Optional[Union[TemplateConfig, InstanceConfig]], str, Optional[Union[PackageView, GlobalResourceView]]],
        ] = {}
        self._status_label = self.create_status_badge(
            "TemplateInstanceStatusBadge",
            "未选中对象",
        )
        self._build_package_membership_row()
        self._build_ui()
        self._connect_signals()
        self.setEnabled(False)

    def _build_ui(self) -> None:
        self.tabs = QtWidgets.QTabWidget()
        self._register_tabs(
            (
                ("basic", "基础信息", lambda: BasicInfoTab(self), True),
                (
                    "graphs",
                    "节点图",
                    lambda: GraphsTab(self, graph_data_provider=self.graph_data_provider),
                    True,
                ),
                ("variables", "自定义变量", lambda: VariablesTab(self), True),
                ("components", "通用组件", lambda: ComponentsTab(self), True),
            )
        )
        self.body_layout.addWidget(self.tabs, 1)

    def _build_package_membership_row(self) -> None:
        """在状态徽章下方构建统一的“所属存档”行。

        设计约定：
        - 模板与实体上下文中，用于管理多对多隶属关系（可被多个存档索引纳入）；
        - 关卡实体上下文中，用作单选行，保持“一个存档至多绑定一个关卡实体”。
        """
        (
            self._package_membership_widget,
            self._package_label,
            self.package_selector,
        ) = build_package_membership_row(
            self.body_layout,
            self,
            self._on_package_membership_changed,
        )
        self._package_membership_widget.setVisible(False)

    def _connect_signals(self) -> None:
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def set_template(self, package: Union[PackageView, GlobalResourceView], template_id: str) -> None:
        self._set_context(package, package.get_template(template_id), "template")

    def set_instance(self, package: Union[PackageView, GlobalResourceView], instance_id: str) -> None:
        self._set_context(package, package.get_instance(instance_id), "instance")

    def set_level_entity(self, package: Union[PackageView, GlobalResourceView]) -> None:
        self._set_context(package, package.level_entity, "level_entity")

    def clear(self) -> None:
        self.current_package = None
        self.current_object = None
        self.object_type = ""
        for tab in self._tab_instances.values():
            tab.clear()
        self._pending_tab_contexts.clear()
        self.setEnabled(False)
        self._update_status_badge(None, "")
        self._clear_package_membership_ui()

    @property
    def basic_tab(self) -> BasicInfoTab:
        return cast(BasicInfoTab, self._ensure_tab_created(self._tab_key_to_index["basic"]))

    @property
    def graphs_tab(self) -> GraphsTab:
        return cast(GraphsTab, self._ensure_tab_created(self._tab_key_to_index["graphs"]))

    @property
    def variables_tab(self) -> VariablesTab:
        return cast(VariablesTab, self._ensure_tab_created(self._tab_key_to_index["variables"]))

    @property
    def components_tab(self) -> ComponentsTab:
        return cast(ComponentsTab, self._ensure_tab_created(self._tab_key_to_index["components"]))

    def _set_context(
        self,
        package: Optional[Union[PackageView, GlobalResourceView]],
        obj: Optional[Union[TemplateConfig, InstanceConfig]],
        object_type: str,
    ) -> None:
        self.current_package = package
        self.current_object = obj
        self.object_type = object_type
        if not obj:
            self.clear()
            return
        self.setEnabled(True)
        self._update_graphs_tab_visibility()
        current_index = self.tabs.currentIndex()
        for index in range(len(self._tab_specs)):
            tab = self._ensure_tab_created(index) if index == current_index else self._tab_instances.get(index)
            if tab and index == current_index:
                tab.set_context(obj, object_type, package, force=True)
                self._pending_tab_contexts.pop(index, None)
            else:
                self._pending_tab_contexts[index] = (obj, object_type, package)
        self._update_status_badge(obj, object_type)
        self._update_package_membership_ui()

    def _update_status_badge(
        self,
        obj: Optional[Union[TemplateConfig, InstanceConfig]],
        object_type: str,
    ) -> None:
        if not obj:
            self._status_label.setText("未选中对象")
            self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_PRIMARY)
            # 未选中对象时使用中性标题，避免误导为固定“元件属性”
            self.set_title("属性")
            return
        if object_type == "template":
            text = f"元件 · {obj.name}"
            color = Colors.PRIMARY
            self.set_title("元件属性")
        elif object_type == "instance":
            text = f"实体 · {obj.name}"
            color = Colors.SUCCESS
            self.set_title("实体属性")
        else:
            text = f"关卡实体 · {obj.name}"
            color = Colors.WARNING
            self.set_title("关卡实体属性")
        self._status_label.setText(text)
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, color)

    def _clear_package_membership_ui(self) -> None:
        """清空并隐藏所属存档选择行。"""
        if hasattr(self, "package_selector"):
            self.package_selector.clear_membership()
            self.package_selector.setEnabled(False)
        if hasattr(self, "_package_membership_widget"):
            self._package_membership_widget.setVisible(False)

    def _update_package_membership_ui(self) -> None:
        """根据当前上下文刷新“所属存档”行。

        设计约定：
        - 模板与实例都可以被多个存档索引纳入，因此使用多选下拉；
        - 关卡实体的归属由面板级单选行管理（保持“每个存档至多一个关卡实体”的约束）。
        """
        manager = self.package_index_manager
        current_object = self.current_object

        if manager is None or current_object is None:
            self._clear_package_membership_ui()
            return

        packages = manager.list_packages()
        if not packages or self.package_selector is None:
            self._clear_package_membership_ui()
            return

        # 模板：扫描 PackageIndex.resources.templates
        if self.object_type == "template" and isinstance(current_object, TemplateConfig):
            template_id = current_object.template_id
            if not template_id:
                self._clear_package_membership_ui()
                return

            membership: set[str] = set()
            for package_info in packages:
                package_id = package_info.get("package_id", "")
                if not package_id:
                    continue
                resources = manager.get_package_resources(package_id)
                if resources and template_id in getattr(resources, "templates", []):
                    membership.add(package_id)

            self.package_selector.set_packages(packages)
            self.package_selector.set_membership(membership)
            self._package_membership_widget.setVisible(True)
            return

        # 实例：扫描 PackageIndex.resources.instances
        if self.object_type == "instance" and isinstance(current_object, InstanceConfig):
            instance_id = current_object.instance_id
            if not instance_id:
                self._clear_package_membership_ui()
                return

            membership = set()
            for package_info in packages:
                package_id = package_info.get("package_id", "")
                if not package_id:
                    continue
                resources = manager.get_package_resources(package_id)
                if resources and instance_id in getattr(resources, "instances", []):
                    membership.add(package_id)

            self.package_selector.set_packages(packages)
            self.package_selector.set_membership(membership)
            self._package_membership_widget.setVisible(True)
            return

        # 关卡实体：使用面板级单选行（保持每个存档至多一个关卡实体）
        if self.object_type == "level_entity" and isinstance(current_object, InstanceConfig):
            self._refresh_level_entity_package_membership(current_object)
            self._package_membership_widget.setVisible(True)
            return

        # 其它上下文不使用面板级控件
        self._clear_package_membership_ui()

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """所属存档复选变化：由面板发射信号写入 PackageIndex 或直接更新索引。

        设计约定：
        - 模板：写入 PackageIndex.resources.templates；
        - 实例：写入 PackageIndex.resources.instances；
        - 关卡实体：直接通过 PackageIndexManager 写回 level_entity_id（保持“每个存档至多一个关卡实体”）。
        """
        if not package_id:
            return

        current_object = self.current_object
        if current_object is None:
            return

        if self.object_type == "template" and isinstance(current_object, TemplateConfig):
            self.template_package_membership_changed.emit(
                current_object.template_id,
                package_id,
                is_checked,
            )
            return

        if self.object_type == "instance" and isinstance(current_object, InstanceConfig):
            self.instance_package_membership_changed.emit(
                current_object.instance_id,
                package_id,
                is_checked,
            )
            return

        if self.object_type == "level_entity" and isinstance(current_object, InstanceConfig):
            self._handle_level_entity_package_change(current_object, package_id, is_checked)
            # 关卡实体归属变化同样视为“数据已更新”，触发持久化链路
            self.data_updated.emit()
            return

    def _refresh_level_entity_package_membership(self, level_entity: InstanceConfig) -> None:
        """根据 PackageIndex.level_entity_id 刷新关卡实体的“所属存档”下拉框。

        约束：
        - 一个存档最多只能绑定一个关卡实体；
        - 下拉框中仅展示“未绑定关卡实体的存档”与“已绑定到当前关卡实体的存档”。
        """
        manager = self.package_index_manager
        selector = self.package_selector
        if manager is None or selector is None:
            if selector is not None:
                selector.clear_membership()
                selector.setEnabled(False)
            return

        packages = manager.list_packages()
        if not packages:
            selector.clear_membership()
            selector.setEnabled(False)
            return

        membership: set[str] = set()
        available_packages: list[dict] = []

        current_package_id = ""
        if isinstance(self.current_package, PackageView):
            current_package_id = getattr(self.current_package, "package_id", "")

        for pkg in packages:
            package_id_value = pkg.get("package_id", "")
            if not package_id_value:
                continue

            if (
                package_id_value == current_package_id
                and isinstance(self.current_package, PackageView)
            ):
                index = self.current_package.package_index
            else:
                index = manager.load_package_index(package_id_value)
            if not index:
                continue

            level_id = index.level_entity_id
            if level_id == level_entity.instance_id:
                membership.add(package_id_value)
                available_packages.append(pkg)
            elif level_id is None:
                available_packages.append(pkg)

        selector.set_packages(available_packages)
        selector.set_membership(membership)
        selector.setEnabled(bool(available_packages))

    def _handle_level_entity_package_change(
        self,
        level_entity: InstanceConfig,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """写回关卡实体的“所属存档”，保持每个存档最多一个关卡实体。

        设计约定：
        - 一个关卡实体要么未绑定存档，要么只绑定一个存档；
        - 一个存档的 level_entity_id 指向至多一个关卡实体；
        - 其它关卡实体在属性页中看不到已经被占用的存档。
        """
        manager = self.package_index_manager
        if manager is None:
            return
        if not package_id:
            return

        target_ids: set[str] = set()
        if is_checked:
            target_ids.add(package_id)

        packages = manager.list_packages()
        current_package_id = ""
        if isinstance(self.current_package, PackageView):
            current_package_id = getattr(self.current_package, "package_id", "")

        for pkg in packages:
            pkg_id = pkg.get("package_id", "")
            if not pkg_id:
                continue

            if (
                pkg_id == current_package_id
                and isinstance(self.current_package, PackageView)
            ):
                index = self.current_package.package_index
            else:
                index = manager.load_package_index(pkg_id)
            if not index:
                continue

            previously_assigned = index.level_entity_id == level_entity.instance_id
            should_be_assigned = pkg_id in target_ids

            if previously_assigned and not should_be_assigned:
                index.level_entity_id = None
                manager.save_package_index(index)
            elif not previously_assigned and should_be_assigned:
                index.level_entity_id = level_entity.instance_id
                if level_entity.instance_id not in index.resources.instances:
                    index.add_instance(level_entity.instance_id)
                manager.save_package_index(index)

        # 写回后刷新当前下拉内容，保证选项列表与选中状态与索引一致
        self._refresh_level_entity_package_membership(level_entity)

    def _register_tabs(
        self,
        specs: tuple[tuple[str, str, Callable[[], TemplateInstanceTabBase], bool], ...],
    ) -> None:
        self._tab_specs = specs
        self._tab_instances: dict[int, TemplateInstanceTabBase] = {}
        self._tab_key_to_index = {key: index for index, (key, _, _, _) in enumerate(specs)}
        for _, title, _, _ in specs:
            self.tabs.addTab(QtWidgets.QWidget(), title)
        self._ensure_tab_created(0)

    def _ensure_tab_created(self, index: int) -> Optional[TemplateInstanceTabBase]:
        if index in self._tab_instances:
            return self._tab_instances[index]
        key, title, factory, auto_emit = self._tab_specs[index]
        tab = factory()
        self._tab_instances[index] = tab
        placeholder = self.tabs.widget(index)
        current_index = self.tabs.currentIndex()
        self.tabs.blockSignals(True)
        self.tabs.removeTab(index)
        if placeholder is not None:
            placeholder.deleteLater()
        self.tabs.insertTab(index, tab, title)
        if current_index == index:
            self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        self._inject_dependencies(tab)
        # 同步只读状态到新创建的标签页
        if self._read_only and hasattr(tab, "set_read_only"):
            tab.set_read_only(True)
        if auto_emit:
            tab.data_changed.connect(self._handle_tab_data_changed)
        if key == "graphs":
            cast(GraphsTab, tab).graph_selected.connect(self.graph_selected.emit)
        pending_context = self._pending_tab_contexts.pop(index, None)
        if pending_context:
            obj, object_type, package = pending_context
            if obj:
                tab.set_context(obj, object_type, package, force=True)
            else:
                tab.clear()
        return tab

    def _inject_dependencies(self, tab: TemplateInstanceTabBase) -> None:
        tab.set_service(self.service)
        if self.resource_manager:
            tab.set_resource_manager(self.resource_manager)
        if self.package_index_manager:
            tab.set_package_index_manager(self.package_index_manager)

    def _configure_tab_dependencies(self) -> None:
        for tab in self._tab_instances.values():
            self._inject_dependencies(tab)

    def _handle_tab_data_changed(self) -> None:
        sender = self.sender()
        basic_tab = self._tab_instances.get(self._tab_key_to_index["basic"])
        if sender is basic_tab:
            self._apply_basic_tab_changes()
        self.data_updated.emit()

    def _apply_basic_tab_changes(self) -> None:
        if not self.current_object:
            return
        payload = self.basic_tab.get_basic_payload()
        self.service.apply_basic_info(self.current_object, payload["name"], payload["description"])
        # GUID 始终通过 metadata['guid'] 统一存储（模板/实例/关卡实体通用）
        self.service.apply_guid(self.current_object, payload.get("guid"))
        drop_metadata = payload.get("drop_metadata")
        if drop_metadata is not None:
            self.service.apply_drop_metadata(self.current_object, drop_metadata)

    def flush_pending_changes(self) -> None:
        """在保存前刷新属性面板中尚未写回模型的基础信息变更。

        设计约定：
        - 仅针对基础信息标签页使用去抖写回的字段（名称/描述/GUID/模型ID 等）；
        - 若基础信息页存在正在等待的去抖触发，这里会显式触发一次数据写回，
          确保后续的 `PackageController.save_package()` 能获取到最新值。
        """
        basic_index = self._tab_key_to_index.get("basic")
        if basic_index is None:
            return
        basic_tab = self._tab_instances.get(basic_index)
        if basic_tab is None:
            basic_tab = self._ensure_tab_created(basic_index)
        if basic_tab is None:
            return
        if hasattr(basic_tab, "flush_pending_changes"):
            basic_tab.flush_pending_changes()
        else:
            self._apply_basic_tab_changes()

    def _on_tab_changed(self, index: int) -> None:
        tab = self._ensure_tab_created(index)
        context = self._pending_tab_contexts.pop(index, None)
        if not context or not tab:
            return
        obj, object_type, package = context
        if obj:
            tab.set_context(obj, object_type, package, force=True)
        else:
            tab.clear()

    # 只读模式 ---------------------------------------------------------------
    def set_read_only(self, read_only: bool) -> None:
        """切换整套元件/实例属性面板的只读状态。

        设计约定：
        - 只读模式下仍可自由切换标签页，但禁用内部所有编辑控件；
        - 外部仍可通过 set_template/set_instance/set_level_entity 更新上下文，用于任务清单等只读预览场景；
        - 在元件库/实体摆放模式中应显式恢复为非只读（由主窗口在模式切换时负责）。
        """
        self._read_only = read_only
        for tab in self._tab_instances.values():
            if hasattr(tab, "set_read_only"):
                tab.set_read_only(read_only)

    # 掉落物上下文辅助 -------------------------------------------------------
    def _is_drop_item_context(self) -> bool:
        """当前面板上下文是否为“掉落物”模板或其实例。"""
        if not self.current_object:
            return False

        if self.object_type == "template" and isinstance(self.current_object, TemplateConfig):
            return is_drop_template_config(self.current_object)

        if self.object_type == "instance" and isinstance(self.current_object, InstanceConfig):
            package = self.current_package
            if isinstance(package, (PackageView, GlobalResourceView)):
                template = package.get_template(self.current_object.template_id)
                return is_drop_template_config(template)

        return False

    def _update_graphs_tab_visibility(self) -> None:
        """根据当前上下文决定是否显示“节点图”标签页。

        掉落物不支持挂接节点图，因此在对应上下文中直接隐藏该标签。
        """
        graphs_index = self._tab_key_to_index.get("graphs")
        if graphs_index is None:
            return

        is_drop_context = self._is_drop_item_context()

        # Qt 5.15+ / Qt6 提供 setTabVisible；如环境不支持则保持现状（回退为仅禁用）
        set_tab_visible = getattr(self.tabs, "setTabVisible", None)
        if callable(set_tab_visible):
            set_tab_visible(graphs_index, not is_drop_context)

        if is_drop_context and self.tabs.currentIndex() == graphs_index:
            basic_index = self._tab_key_to_index.get("basic")
            if basic_index is not None:
                self.tabs.setCurrentIndex(basic_index)


