from __future__ import annotations

from .bridge_base import _UiWorkbenchBridgeBase
from .bridge_catalog_ui import _UiWorkbenchBridgeUiCatalogMixin
from .bridge_export import _UiWorkbenchBridgeExportMixin
from .bridge_import_variable_defaults import _UiWorkbenchBridgeImportVariableDefaultsMixin
from .bridge_import_layouts import _UiWorkbenchBridgeImportLayoutsMixin
from .bridge_import_ui_pages import _UiWorkbenchBridgeImportUiPagesMixin
from .bridge_internal import _UiWorkbenchBridgeInternalMixin
from .bridge_placeholder_validation import _UiWorkbenchBridgePlaceholderValidationMixin


class _UiWorkbenchBridge(
    _UiWorkbenchBridgeBase,
    _UiWorkbenchBridgeUiCatalogMixin,
    _UiWorkbenchBridgePlaceholderValidationMixin,
    _UiWorkbenchBridgeImportVariableDefaultsMixin,
    _UiWorkbenchBridgeExportMixin,
    _UiWorkbenchBridgeImportLayoutsMixin,
    _UiWorkbenchBridgeImportUiPagesMixin,
    _UiWorkbenchBridgeInternalMixin,
):
    """
    兼容层：保持私有扩展 `plugin.py` 原有对外类名 `_UiWorkbenchBridge`。

    实现被拆分为多个 mixin，以控制单文件行数并保持职责清晰。
    """

    pass

