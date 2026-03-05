"""管理配置库页面用的 Section 基类与通用数据结构与依赖。

原始的 `management_sections.py` 体量较大，已拆分为多个子模块。
本模块集中承载所有 Section 共享的类型别名、数据结构与基础依赖，
其他子模块通过 `from .management_sections_base import *` 复用这些定义。

资源语义约定（与资源库布局文档保持一致）：
- 管理配置资源的**本体**是一份 JSON 文件，物理位置位于某个资源根目录下的 `管理配置/**.json`，
  例如 `assets/资源库/项目存档/<package_id>/管理配置/**.json`（共享根同理）。
- 存档视图在 `PackageIndex.resources.management[...]` 中以“资源 ID 列表”的形式引用这些 JSON，
  该列表在目录模式下由“文件物理位置”派生（不再写回任何 pkg_*.json 旧式索引文件）。
- Section 与管理页面通过 `PackageView/GlobalResourceView.management` 访问的是
  这些 JSON 的视图模型；在具体存档视图下，`PackageController._sync_management_resources_to_index()`
  负责将视图模型写回对应的 JSON 文件并刷新存档索引（PackageIndex）视图；在全局视图下当前实现主要用于聚合浏览。
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import types
from typing import Iterable, Tuple, Union, Optional, Dict, Any, Sequence, List, Mapping, cast, Callable

from PyQt6 import QtCore, QtWidgets

from engine.configs.management.level_settings_configs import LevelSettingsConfig
from engine.configs.management.resource_language_configs import SkillResourceConfig
from engine.configs.management.audio_music_configs import BackgroundMusicConfig
from engine.configs.management.shop_economy_configs import (
    CurrencyBackpackConfig,
    CurrencyConfig,
    EquipmentDataConfig,
    ShopTemplateConfig,
)
from engine.configs.management.save_point_configs import SavePointConfig
from engine.configs.management.deployment_configs import EntityDeploymentGroupConfig
from engine.configs.management.timer_variable_configs import (
    LevelVariableConfig,
    TimerManagementConfig,
)
from engine.configs.management.tag_shield_configs import (
    UnitTagConfig,
    ShieldConfig,
    ScanTagConfig,
)
from engine.configs.management.light_configs import LightSourceConfig
from engine.configs.management.chat_configs import ChatChannelConfig
from engine.configs.resource_types import ResourceType
from engine.configs.specialized.node_graph_configs import (
    StructDefinition as NodeGraphStructDefinition,
)
from engine.graph.models.package_model import SignalConfig, SignalParameterConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from engine.validate.comprehensive_rules.helpers import iter_all_package_graphs
from app.ui.dialogs.signal_edit_dialog import SignalEditDialog
from app.ui.dialogs.struct_definition_dialog import (
    StructDefinitionDialog,
    normalize_canonical_type_name,
    param_type_to_canonical,
)
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.theme_manager import ThemeManager
from app.ui.forms.schema_dialog import FormDialogBuilder


ManagementPackage = Union[PackageView, GlobalResourceView]


@dataclass
class ManagementRowData:
    """描述管理配置列表中一行需要展示的聚合信息。"""

    name: str
    type_name: str
    attr1: str
    attr2: str
    attr3: str
    description: str
    last_modified: str
    user_data: Tuple[str, str]


class BaseManagementSection:
    """管理配置 Section 通用接口。

    一个 Section 对应管理域中的一种资源类型（例如“计时器”“关卡变量”“预设点”），
    负责在给定 Package 视图下：
    - 枚举该类型的所有记录；
    - 提供统一的增删改入口。
    """

    section_key: str
    tree_label: str
    type_name: str

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        raise NotImplementedError

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        raise NotImplementedError

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        raise NotImplementedError

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        raise NotImplementedError

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """可选：为管理模式右侧属性面板提供就地编辑表单。

        默认返回 None，表示该 Section 仍使用只读摘要模式。
        需要右侧编辑能力的 Section 可以重写本方法，返回：
        - title: 面板标题
        - description: 面板说明
        - build_form(form_layout): 在给定的表单布局中构建具体控件，并在字段变化时调用 on_changed()。
        """
        _ = (parent, package, item_id, on_changed)
        return None

    def set_usage_text(self, usage_text: str) -> None:
        """可选：设置“被引用/使用情况”等辅助文本（默认无行为）。

        说明：
        - 该接口用于消除上层对具体 Section 的反射式调用（hasattr/getattr）。
        - 只有少数 Section（例如关卡变量分组）需要在列表选择时动态回填“被哪些存档引用”。
        """
        _ = usage_text

    @staticmethod
    def _get_last_modified_text(payload: Dict[str, Any]) -> str:
        raw_value = payload.get("last_modified")
        return str(raw_value) if raw_value is not None else ""



