from __future__ import annotations

"""主镜头管理右侧编辑面板。

作为主窗口右侧标签页中的一个面板，用于在“管理面板”模式下
编辑当前选中的主镜头配置：

- 左侧列表由 `ManagementLibraryWidget` 与 `MainCameraSection` 提供；
- 本面板只负责展示与编辑单个主镜头的详细参数；
- 保存后通过 `data_updated` 信号通知主窗口刷新列表并立即持久化。
"""

from typing import Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from ui.foundation.theme_manager import Sizes
from ui.panels.panel_scaffold import PanelScaffold
from ui.panels.package_membership_selector import (
    PackageMembershipSelector,
    build_package_membership_row,
)


ManagementPackage = Union[PackageView, GlobalResourceView]


class MainCameraManagementPanel(PanelScaffold):
    """主镜头管理右侧编辑面板。

    约定：
    - 左侧“主镜头管理”列表负责选择具体镜头；
    - 本面板接收 (package, camera_id) 上下文并展示可编辑表单；
    - 顶部通过统一的“所属存档”多选行维护主镜头与功能包之间的多对多归属关系；
    - 点击“保存主镜头”按钮后，将修改写回 `package.management.main_cameras[camera_id]`
      并发射 `data_updated` 信号，由主窗口统一刷新与持久化。
    """

    # 主镜头所属存档变更 (camera_id, package_id, is_checked)
    camera_package_membership_changed = QtCore.pyqtSignal(str, str, bool)

    data_updated = QtCore.pyqtSignal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="主镜头详情",
            description="在左侧列表中选择一个主镜头后，在此编辑其参数。",
        )
        self._current_package: Optional[ManagementPackage] = None
        self._current_camera_id: Optional[str] = None

        self._package_row_widget: Optional[QtWidgets.QWidget] = None
        self._package_label: Optional[QtWidgets.QLabel] = None
        self._package_selector: Optional[PackageMembershipSelector] = None

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
        if self._package_selector is not None:
            self._package_selector.setEnabled(False)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        form_container = QtWidgets.QWidget()
        form_layout = QtWidgets.QFormLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        scroll_area.setWidget(form_container)
        self.body_layout.addWidget(scroll_area, 1)

        # --- 字段控件 --------------------------------------------------------
        self.id_label = QtWidgets.QLabel("-")
        form_layout.addRow("镜头ID:", self.id_label)

        self.name_edit = QtWidgets.QLineEdit()
        form_layout.addRow("镜头名称:", self.name_edit)

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["follow", "fixed", "path", "custom"])
        form_layout.addRow("镜头类型:", self.type_combo)

        self.fov_spin = QtWidgets.QDoubleSpinBox()
        self.fov_spin.setRange(30.0, 120.0)
        self.fov_spin.setSingleStep(1.0)
        self.fov_spin.setDecimals(1)
        self.fov_spin.setSuffix("°")
        form_layout.addRow("视野角度(FOV):", self.fov_spin)

        self.near_spin = QtWidgets.QDoubleSpinBox()
        self.near_spin.setRange(0.01, 10.0)
        self.near_spin.setSingleStep(0.01)
        self.near_spin.setDecimals(2)
        form_layout.addRow("近裁剪面:", self.near_spin)

        self.far_spin = QtWidgets.QDoubleSpinBox()
        self.far_spin.setRange(100.0, 10000.0)
        self.far_spin.setSingleStep(10.0)
        self.far_spin.setDecimals(1)
        form_layout.addRow("远裁剪面:", self.far_spin)

        self.follow_target_edit = QtWidgets.QLineEdit()
        self.follow_target_edit.setPlaceholderText("目标实体ID")
        form_layout.addRow("跟随目标:", self.follow_target_edit)

        self.follow_distance_spin = QtWidgets.QDoubleSpinBox()
        self.follow_distance_spin.setRange(0.0, 100.0)
        self.follow_distance_spin.setSingleStep(0.5)
        self.follow_distance_spin.setDecimals(2)
        form_layout.addRow("跟随距离:", self.follow_distance_spin)

        self.follow_height_spin = QtWidgets.QDoubleSpinBox()
        self.follow_height_spin.setRange(-50.0, 50.0)
        self.follow_height_spin.setSingleStep(0.5)
        self.follow_height_spin.setDecimals(2)
        form_layout.addRow("跟随高度:", self.follow_height_spin)

        self.description_edit = QtWidgets.QTextEdit()
        self.description_edit.setMinimumHeight(80)
        self.description_edit.setMaximumHeight(200)
        form_layout.addRow("描述:", self.description_edit)

        # --- 操作区：保存按钮 -------------------------------------------------
        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch(1)

        self.save_button = QtWidgets.QPushButton("保存主镜头")
        self.save_button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        self.save_button.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_button)

        self.body_layout.addLayout(button_row)

        self.setEnabled(False)

    # ------------------------------------------------------------------ 对外接口

    def clear(self) -> None:
        """清空当前上下文并重置表单。"""
        self._current_package = None
        self._current_camera_id = None

        if self._package_selector is not None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

        self.id_label.setText("-")
        self.name_edit.clear()
        self.type_combo.setCurrentIndex(0)
        self.fov_spin.setValue(90.0)
        self.near_spin.setValue(0.1)
        self.far_spin.setValue(1000.0)
        self.follow_target_edit.clear()
        self.follow_distance_spin.setValue(5.0)
        self.follow_height_spin.setValue(2.0)
        self.description_edit.clear()

        self.setEnabled(False)

    def set_context(self, package: ManagementPackage, camera_id: str) -> None:
        """设置当前编辑上下文并加载镜头数据。"""
        self._current_package = package
        self._current_camera_id = camera_id

        cameras = getattr(package.management, "main_cameras", None)
        if not isinstance(cameras, dict):
            self.clear()
            return
        if camera_id not in cameras:
            self.clear()
            return

        payload = cameras[camera_id]
        if not isinstance(payload, dict):
            self.clear()
            return

        self._load_from_payload(camera_id, payload)
        self.setEnabled(True)

    def set_current_camera_id(self, camera_id: Optional[str]) -> None:
        """更新当前正在编辑的主镜头 ID，用于归属变更信号携带完整上下文。"""
        self._current_camera_id = camera_id
        if camera_id is None and self._package_selector is not None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

    def set_camera_membership(
        self,
        packages: list[dict],
        membership: set[str],
    ) -> None:
        """根据给定包列表与归属集合更新“所属存档”多选下拉状态。"""
        selector = self._package_selector
        if selector is None:
            return
        if not packages:
            selector.clear_membership()
            selector.setEnabled(False)
            return
        selector.set_packages(packages)
        selector.set_membership(membership)
        selector.setEnabled(self._current_camera_id is not None)

    # ------------------------------------------------------------------ 内部逻辑

    def _load_from_payload(self, camera_id: str, payload: dict) -> None:
        """根据字典载入表单字段。"""
        self.id_label.setText(str(camera_id))
        self.name_edit.setText(str(payload.get("camera_name", "")))

        camera_type_value = str(payload.get("camera_type", "follow"))
        type_index = self.type_combo.findText(camera_type_value)
        if type_index == -1:
            type_index = 0
        self.type_combo.setCurrentIndex(type_index)

        self.fov_spin.setValue(float(payload.get("fov", 90.0)))
        self.near_spin.setValue(float(payload.get("near_clip", 0.1)))
        self.far_spin.setValue(float(payload.get("far_clip", 1000.0)))
        self.follow_target_edit.setText(str(payload.get("follow_target", "")))
        self.follow_distance_spin.setValue(float(payload.get("follow_distance", 5.0)))
        self.follow_height_spin.setValue(float(payload.get("follow_height", 2.0)))
        self.description_edit.setPlainText(str(payload.get("description", "")))

    def _on_save_clicked(self) -> None:
        """保存当前镜头到包内管理配置。"""
        if self._current_package is None:
            return
        if self._current_camera_id is None:
            return

        cameras = getattr(self._current_package.management, "main_cameras", None)
        if not isinstance(cameras, dict):
            return
        if self._current_camera_id not in cameras:
            return

        payload = cameras[self._current_camera_id]
        if not isinstance(payload, dict):
            payload = {}

        payload["camera_id"] = self._current_camera_id
        payload["camera_name"] = self.name_edit.text().strip()
        payload["camera_type"] = str(self.type_combo.currentText())
        payload["fov"] = float(self.fov_spin.value())
        payload["near_clip"] = float(self.near_spin.value())
        payload["far_clip"] = float(self.far_spin.value())
        payload["follow_target"] = self.follow_target_edit.text().strip()
        payload["follow_distance"] = float(self.follow_distance_spin.value())
        payload["follow_height"] = float(self.follow_height_spin.value())
        payload["description"] = self.description_edit.toPlainText().strip()

        cameras[self._current_camera_id] = payload
        self.data_updated.emit()

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """用户在“所属存档”多选行中勾选/取消某个存档时触发。"""
        if not package_id:
            return
        if not self._current_camera_id:
            return
        self.camera_package_membership_changed.emit(
            self._current_camera_id,
            package_id,
            is_checked,
        )


__all__ = ["MainCameraManagementPanel"]


