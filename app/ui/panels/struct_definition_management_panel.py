from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Set, Tuple

from PyQt6 import QtCore, QtWidgets

from engine.configs.specialized.node_graph_configs import (
    StructDefinition as NodeGraphStructDefinition,
)
from ui.dialogs.struct_definition_dialog import StructDefinitionEditorWidget
from ui.dialogs.struct_definition_types import normalize_canonical_type_name
from ui.foundation.theme_manager import Sizes
from ui.panels.package_membership_selector import (
    PackageMembershipSelector,
    build_package_membership_row,
)
from ui.panels.panel_scaffold import PanelScaffold


class StructDefinitionManagementPanel(PanelScaffold):
    """结构体定义右侧编辑面板。

    用于在管理模式下承载结构体的基础信息与字段编辑界面：
    - 顶部使用 `build_package_membership_row` 提供统一的“所属存档”多选行；
    - “基本信息”标签页中嵌入 `StructDefinitionEditorWidget`，编辑结构体名与字段列表；
    - 标题与说明文本用于提示当前上下文（查看/新建/编辑）。

    本面板只负责 UI 组织与当前结构体 ID 的记录，实际数据加载与保存由上层主窗口负责。
    """

    # 结构体所属存档变更 (struct_id, package_id, is_checked)
    struct_package_membership_changed = QtCore.pyqtSignal(str, str, bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="结构体详情",
            description=(
                "结构体定义已迁移为代码级常量：左侧选择结构体以查看字段与类型，"
                "实际增删改请在对应的 Python 模块中完成。"
            ),
        )
        self._current_struct_id: Optional[str] = None
        self._package_row_widget: QtWidgets.QWidget
        self._package_label: QtWidgets.QLabel
        self._package_selector: PackageMembershipSelector
        self._field_count_label: QtWidgets.QLabel
        self.tab_widget: QtWidgets.QTabWidget
        self.editor: StructDefinitionEditorWidget

        (
            self._package_row_widget,
            self._package_label,
            self._package_selector,
        ) = build_package_membership_row(
            self.body_layout,
            self,
            self._on_package_membership_changed,
            label_text="所属存档:",
        )
        self._package_selector.setEnabled(False)

        self.tab_widget = QtWidgets.QTabWidget(self)
        self.body_layout.addWidget(self.tab_widget, 1)

        basic_tab = QtWidgets.QWidget(self.tab_widget)
        basic_layout = QtWidgets.QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(0, 0, 0, 0)
        basic_layout.setSpacing(Sizes.SPACING_MEDIUM)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setLabelAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        form_layout.setFormAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
        )
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self._field_count_label = QtWidgets.QLabel("-")
        form_layout.addRow("字段数量:", self._field_count_label)
        basic_layout.addLayout(form_layout)

        supported_types = self._build_supported_types()
        self.editor = StructDefinitionEditorWidget(
            parent=basic_tab,
            supported_types=supported_types,
        )
        basic_layout.addWidget(self.editor, 1)

        self.tab_widget.addTab(basic_tab, "基本信息")

        # 管理模式下结构体详情面板当前仅作为只读视图使用，实际定义在代码中维护。
        # 弹窗等其它入口若需要可编辑能力，可直接使用 `StructDefinitionEditorWidget` 并保持默认状态。
        self.editor.set_read_only(True)

    @staticmethod
    def _build_supported_types() -> Sequence[str]:
        """从节点图配置中获取结构体字段可选的数据类型列表（规范中文名去重）。"""
        struct_definition_config = NodeGraphStructDefinition()
        raw_types = struct_definition_config.supported_types
        if not isinstance(raw_types, Sequence):
            return []

        normalized: List[str] = []
        seen: Set[str] = set()
        for raw in raw_types:
            if not isinstance(raw, str):
                continue
            canonical = normalize_canonical_type_name(raw)
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            normalized.append(canonical)
        return normalized

    # ------------------------------------------------------------------ 对外接口

    def set_current_struct_id(self, struct_id: Optional[str]) -> None:
        """更新当前正在编辑的结构体 ID，用于在归属变更时发射完整上下文。"""
        self._current_struct_id = struct_id
        if struct_id is None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

    def set_packages_and_membership(
        self,
        packages: Sequence[dict],
        membership: Iterable[str],
    ) -> None:
        """根据给定包列表与归属集合更新多选下拉状态。"""
        if not packages:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)
            return
        self._package_selector.set_packages(list(packages))
        self._package_selector.set_membership(set(membership))
        self._package_selector.setEnabled(self._current_struct_id is not None)

    def set_field_count(self, count: int) -> None:
        """更新字段数量显示。"""
        self._field_count_label.setText(str(int(count)))

    def reset(self) -> None:
        """清空右侧编辑器显示，但保留控件结构。"""
        self._current_struct_id = None
        self._package_selector.clear_membership()
        self._package_selector.setEnabled(False)
        self._field_count_label.setText("-")
        self.editor.load_struct(struct_name="", fields=[], allow_edit_name=False)
        self.tab_widget.setCurrentIndex(0)

    # ------------------------------------------------------------------ 内部回调

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """用户在“所属存档”多选下拉中勾选/取消某个存档时触发。"""
        if not package_id:
            return
        if not self._current_struct_id:
            return
        self.struct_package_membership_changed.emit(
            self._current_struct_id,
            package_id,
            is_checked,
        )


__all__ = ["StructDefinitionManagementPanel"]


