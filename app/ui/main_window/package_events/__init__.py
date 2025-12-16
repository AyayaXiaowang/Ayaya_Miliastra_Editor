"""`ui.main_window.package_events` - 存档/资源索引相关事件处理的拆分实现。

该子包仅承载拆分后的多个 Mixin，小文件内聚，避免单个事件文件过大。
对外仍由 `ui.main_window.package_events_mixin.PackageEventsMixin` 作为稳定入口导出。
"""

from __future__ import annotations

from .package_load_save_mixin import PackageLoadSaveMixin
from .library_selection_mixin import LibrarySelectionMixin
from .packages_view_mixin import PackagesViewMixin
from .management_panels_mixin import ManagementPanelsMixin
from .membership_mixin import MembershipMixin
from .immediate_persist_mixin import ImmediatePersistMixin
from .resource_membership_mixin import ResourceMembershipMixin

__all__ = [
    "PackageLoadSaveMixin",
    "LibrarySelectionMixin",
    "PackagesViewMixin",
    "ManagementPanelsMixin",
    "MembershipMixin",
    "ImmediatePersistMixin",
    "ResourceMembershipMixin",
]


