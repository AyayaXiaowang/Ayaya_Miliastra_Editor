from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Sequence, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from app.ui.panels.panel_scaffold import PanelScaffold
from app.ui.panels.package_membership_selector import (
    PackageMembershipSelector,
    build_package_membership_row,
)
from app.ui.panels.peripheral_system.achievement_tab import PeripheralAchievementTab
from app.ui.panels.peripheral_system.leaderboard_tab import PeripheralLeaderboardTab
from app.ui.panels.peripheral_system.rank_tab import PeripheralRankTab


ManagementPackage = Union[PackageView, GlobalResourceView]


class PeripheralSystemManagementPanel(PanelScaffold):
    """外围系统管理右侧编辑面板（薄壳编排器）。

    结构约定（与 `ManagementData.peripheral_systems` 对齐）：
    - management.peripheral_systems: {system_id: system_payload, ...}
    - system_payload 字段：
        - system_id: str
        - system_name: str
        - name: str  # 兼容通用展示逻辑
        - description: str
        - leaderboard_settings: {enabled, allow_room_settle, records: [...]}
        - competitive_rank_settings: {enabled, allow_room_settle, note, score_groups: [...]}
        - achievement_settings: {enabled, allow_room_settle, extreme_enabled, items: [...]}
        - last_modified: str

    本面板只负责就地编辑上述结构，实际持久化由 PackageController 统一处理。
    """

    data_updated = QtCore.pyqtSignal()
    # 外围系统所属存档变更 (system_id, package_id, is_checked)
    system_package_membership_changed = QtCore.pyqtSignal(str, str, bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="外围系统详情",
            description="配置外围系统模板的排行榜、竞技段位与成就。",
        )

        self.current_package: Optional[ManagementPackage] = None
        self.current_system_id: Optional[str] = None
        self.current_system_payload: Optional[Dict[str, Any]] = None

        # 顶部“所属存档”多选行
        self._package_row_widget: QtWidgets.QWidget
        self._package_label: QtWidgets.QLabel
        self._package_selector: PackageMembershipSelector

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

        self.tabs = QtWidgets.QTabWidget()
        self.body_layout.addWidget(self.tabs, 1)

        self.leaderboard_tab = PeripheralLeaderboardTab(self.tabs)
        self.rank_tab = PeripheralRankTab(self.tabs)
        self.achievement_tab = PeripheralAchievementTab(self.tabs)

        self.tabs.addTab(self.leaderboard_tab, "排行榜")
        self.tabs.addTab(self.rank_tab, "竞技段位")
        self.tabs.addTab(self.achievement_tab, "成就")

        self.leaderboard_tab.data_updated.connect(self._on_child_tab_data_updated)
        self.rank_tab.data_updated.connect(self._on_child_tab_data_updated)
        self.achievement_tab.data_updated.connect(self._on_child_tab_data_updated)

        self.setEnabled(False)

    # ------------------------------------------------------------------ 公共接口

    def clear(self) -> None:
        """清空当前上下文与表单内容。"""
        self.current_package = None
        self.current_system_id = None
        self.current_system_payload = None

        self._package_selector.clear_membership()
        self._package_selector.setEnabled(False)

        self.leaderboard_tab.clear()
        self.rank_tab.clear()
        self.achievement_tab.clear()

        self.setEnabled(False)

    def set_context(self, package: ManagementPackage, system_id: str) -> None:
        """更新当前外围系统模板上下文并刷新三个标签页。"""
        self.current_package = package
        self.current_system_id = system_id

        container_any = package.management.peripheral_systems
        if not isinstance(container_any, dict):
            self.clear()
            return
        payload_any = container_any.get(system_id)
        if not isinstance(payload_any, dict):
            self.clear()
            return

        self.current_system_payload = payload_any
        self._ensure_system_structure()

        system_name_text = str(payload_any.get("system_name", "")).strip() or system_id
        self.set_title(f"外围系统：{system_name_text}")

        self.leaderboard_tab.set_system_payload(self.current_system_payload)
        self.rank_tab.set_system_payload(self.current_system_payload)
        self.achievement_tab.set_system_payload(self.current_system_payload)

        self.setEnabled(True)

    # ------------------------------------------------------------------ 所属存档（外围系统模板）

    def set_current_system_id(self, system_id: Optional[str]) -> None:
        """更新当前正在编辑的外围系统模板 ID，用于在归属变更时发射完整上下文。"""
        self.current_system_id = system_id
        if system_id is None:
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
        self._package_selector.setEnabled(self.current_system_id is not None)

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """用户在“所属存档”多选下拉中勾选/取消某个存档时触发。"""
        if not package_id:
            return
        if not self.current_system_id:
            return
        self.system_package_membership_changed.emit(
            self.current_system_id,
            package_id,
            is_checked,
        )

    # ------------------------------------------------------------------ 内部：统一变更处理

    def _on_child_tab_data_updated(self) -> None:
        """子 Tab 修改了 payload 时，统一更新 last_modified 并向外发射 data_updated。"""
        self._mark_system_modified()

    def _ensure_system_structure(self) -> None:
        """确保当前模板下的三个子配置体结构存在。"""
        if self.current_system_payload is None:
            return

        payload = self.current_system_payload

        system_id_text = str(payload.get("system_id", self.current_system_id or "")).strip()
        if not system_id_text and self.current_system_id:
            system_id_text = self.current_system_id
            payload["system_id"] = system_id_text

        system_name_text = str(payload.get("system_name", "")).strip()
        if not system_name_text and system_id_text:
            system_name_text = system_id_text
            payload["system_name"] = system_name_text
        if "name" not in payload:
            payload["name"] = system_name_text or system_id_text

        for key, default_value in [
            (
                "leaderboard_settings",
                {"enabled": False, "allow_room_settle": False, "records": []},
            ),
            (
                "competitive_rank_settings",
                {
                    "enabled": False,
                    "allow_room_settle": False,
                    "note": "",
                    "score_groups": [],
                },
            ),
            (
                "achievement_settings",
                {
                    "enabled": False,
                    "allow_room_settle": False,
                    "extreme_enabled": False,
                    "items": [],
                },
            ),
        ]:
            value_any = payload.get(key)
            if not isinstance(value_any, dict):
                payload[key] = dict(default_value)

    def _mark_system_modified(self) -> None:
        if self.current_system_payload is None:
            return
        self.current_system_payload["last_modified"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.data_updated.emit()


__all__ = ["PeripheralSystemManagementPanel"]


