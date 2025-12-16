"""存档与资源索引相关的事件处理 Mixin

注意：本文件仅作为**对外稳定入口**与聚合继承点。
具体实现已按职责拆分到 `ui/main_window/package_events/` 子包中，避免单文件过大。
"""

from __future__ import annotations

from .package_events.immediate_persist_mixin import ImmediatePersistMixin
from .package_events.library_selection_mixin import LibrarySelectionMixin
from .package_events.management_panels_mixin import ManagementPanelsMixin
from .package_events.membership_mixin import MembershipMixin
from .package_events.package_load_save_mixin import PackageLoadSaveMixin
from .package_events.packages_view_mixin import PackagesViewMixin
from .package_events.resource_membership_mixin import ResourceMembershipMixin


class PackageEventsMixin(  # noqa: D101
    PackageLoadSaveMixin,
    LibrarySelectionMixin,
    PackagesViewMixin,
    ManagementPanelsMixin,
    MembershipMixin,
    ImmediatePersistMixin,
    ResourceMembershipMixin,
):
    """负责存档加载/保存、下拉框刷新以及资源归属变更等事件处理逻辑。"""

    ...


