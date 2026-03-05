from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol

from app.models.todo_item import TodoItem
from app.ui.todo.detail.todo_detail_model import DetailDocument


@dataclass(frozen=True, slots=True)
class TodoDetailBuildContext:
    """Todo 详情文档构建所需的依赖与回调集合。

    说明：
    - 该对象应保持无 Qt 依赖，便于单测与纯逻辑复用。
    - 扩展 detail_type 的构建逻辑时，应通过 registry 注册新的 builder，
      避免回到中心化 if-chain。
    """

    collect_categories_info: Callable[[object], Dict[str, list]]
    collect_category_items: Callable[[object], list]
    collect_template_summary: Callable[[object], Dict[str, int]]
    collect_instance_summary: Callable[[object], Dict[str, int]]


class DetailDocumentBuilder(Protocol):
    def __call__(
        self,
        context: TodoDetailBuildContext,
        todo: TodoItem,
        info: dict,
        detail_type: str,
    ) -> DetailDocument: ...


_builders_by_type: Dict[str, DetailDocumentBuilder] = {}
_prefix_builders: List[tuple[str, DetailDocumentBuilder]] = []
_predicate_builders: List[tuple[Callable[[str, dict], bool], DetailDocumentBuilder]] = []
_fallback_builder: Optional[DetailDocumentBuilder] = None

_plugins_loaded: bool = False
_imported_plugin_modules: set[str] = set()

_PLUGIN_PACKAGE = "app.ui.todo.detail.builders"
_FALLBACK_MODULE = f"{_PLUGIN_PACKAGE}.fallback"

# 按需加载规则：尽量避免在 UI 线程首次打开详情时一次性 import 全量插件模块。
# 注意：
# - 精确类型优先（用于处理与前缀冲突的类型，例如 graph_variables_table）。
# - 若未命中规则且查不到 builder，会回退到“全量加载插件并重试”，保证兼容新增插件模块。
_EXACT_TYPE_TO_MODULE: dict[str, str] = {
    # root/category
    "root": f"{_PLUGIN_PACKAGE}.root_and_category",
    "category": f"{_PLUGIN_PACKAGE}.root_and_category",
    # template/instance
    "template": f"{_PLUGIN_PACKAGE}.template_and_instance",
    "template_basic": f"{_PLUGIN_PACKAGE}.template_and_instance",
    "template_variables_table": f"{_PLUGIN_PACKAGE}.template_and_instance",
    "graph_variables_table": f"{_PLUGIN_PACKAGE}.template_and_instance",
    "template_components_table": f"{_PLUGIN_PACKAGE}.template_and_instance",
    "instance": f"{_PLUGIN_PACKAGE}.template_and_instance",
    "instance_properties_table": f"{_PLUGIN_PACKAGE}.template_and_instance",
    # graph
    "template_graph_root": f"{_PLUGIN_PACKAGE}.graph_related",
    "event_flow_root": f"{_PLUGIN_PACKAGE}.graph_related",
}
_PREFIX_TO_MODULE: list[tuple[str, str]] = [
    ("graph_", f"{_PLUGIN_PACKAGE}.graph_related"),
    ("composite_", f"{_PLUGIN_PACKAGE}.composite"),
    ("combat_", f"{_PLUGIN_PACKAGE}.combat_and_management"),
    ("management_", f"{_PLUGIN_PACKAGE}.combat_and_management"),
]


def _import_plugin_module(module_name: str) -> None:
    normalized = str(module_name or "").strip()
    if not normalized:
        return
    if normalized in _imported_plugin_modules:
        return
    importlib.import_module(normalized)
    _imported_plugin_modules.add(normalized)


def _ensure_fallback_builder_loaded() -> None:
    _import_plugin_module(_FALLBACK_MODULE)


def register_detail_type(detail_type: str) -> Callable[[DetailDocumentBuilder], DetailDocumentBuilder]:
    """注册精确 detail_type 的文档构建器。"""

    def decorator(builder: DetailDocumentBuilder) -> DetailDocumentBuilder:
        normalized_type = str(detail_type or "")
        _builders_by_type[normalized_type] = builder
        return builder

    return decorator


def register_detail_prefix(prefix: str) -> Callable[[DetailDocumentBuilder], DetailDocumentBuilder]:
    """注册 detail_type 前缀匹配的文档构建器（例如 combat_*）。"""

    def decorator(builder: DetailDocumentBuilder) -> DetailDocumentBuilder:
        normalized_prefix = str(prefix or "")
        _prefix_builders.append((normalized_prefix, builder))
        return builder

    return decorator


def register_detail_predicate(
    predicate: Callable[[str, dict], bool],
) -> Callable[[DetailDocumentBuilder], DetailDocumentBuilder]:
    """注册自定义谓词的文档构建器（用于复杂匹配规则）。"""

    def decorator(builder: DetailDocumentBuilder) -> DetailDocumentBuilder:
        _predicate_builders.append((predicate, builder))
        return builder

    return decorator


def register_fallback_detail_builder(builder: DetailDocumentBuilder) -> DetailDocumentBuilder:
    """注册兜底构建器：当所有规则都无法匹配时使用。"""
    global _fallback_builder
    _fallback_builder = builder
    return builder


def ensure_detail_builder_plugins_loaded() -> None:
    """加载 app.ui.todo.detail.builders 下的所有模块，触发其注册行为。

    用途：
    - 诊断/测试：列出所有可用 detail_type；
    - 兜底：当按需加载未命中且找不到 builder 时，全量加载再重试。
    """
    global _plugins_loaded
    if _plugins_loaded:
        return

    _ensure_fallback_builder_loaded()
    package = importlib.import_module(_PLUGIN_PACKAGE)
    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        _import_plugin_module(module_info.name)

    _plugins_loaded = True


def ensure_detail_builder_plugins_loaded_for_detail_type(detail_type: str) -> None:
    """按需加载与某个 detail_type 最相关的 builder 插件模块。

    目标：降低首次打开详情面板时的 import 链成本，避免 UI 主线程长时间卡顿。
    """

    normalized_type = str(detail_type or "")
    _ensure_fallback_builder_loaded()

    exact_module = _EXACT_TYPE_TO_MODULE.get(normalized_type)
    if exact_module is not None:
        _import_plugin_module(exact_module)
        return

    for prefix, module_name in list(_PREFIX_TO_MODULE):
        if normalized_type.startswith(prefix):
            _import_plugin_module(module_name)
            return


def _resolve_builder(detail_type: str, info: dict) -> Optional[DetailDocumentBuilder]:
    direct_builder = _builders_by_type.get(detail_type)
    if direct_builder is not None:
        return direct_builder

    for prefix, builder in _prefix_builders:
        if detail_type.startswith(prefix):
            return builder

    for predicate, builder in _predicate_builders:
        if predicate(detail_type, info):
            return builder

    return None


def list_registered_detail_types() -> list[str]:
    """列出已注册的精确 detail_type（用于测试/诊断）。

    注意：该函数只返回精确匹配的类型键；前缀/predicate 规则需通过对应接口获取。
    """

    ensure_detail_builder_plugins_loaded()
    return sorted(_builders_by_type.keys())


def list_registered_detail_prefixes() -> list[str]:
    """列出已注册的 detail_type 前缀规则（例如 combat_）。"""

    ensure_detail_builder_plugins_loaded()
    prefixes: list[str] = []
    for prefix, _builder in _prefix_builders:
        prefixes.append(prefix)
    return prefixes


def build_detail_document(
    context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    detail_type: str,
) -> DetailDocument:
    """根据 detail_type 选择对应的 builder，并构建 DetailDocument。"""
    normalized_type = str(detail_type or "")
    ensure_detail_builder_plugins_loaded_for_detail_type(normalized_type)

    builder = _resolve_builder(normalized_type, info)
    if builder is None and not _plugins_loaded:
        # 兜底：按需加载规则未覆盖的插件模块（例如新增的 detail_builders 模块）
        ensure_detail_builder_plugins_loaded()
        builder = _resolve_builder(normalized_type, info)

    if builder is None:
        if _fallback_builder is None:
            raise RuntimeError("TodoDetailBuilder registry 未注册 fallback builder")
        builder = _fallback_builder

    return builder(context, todo, info, normalized_type)


