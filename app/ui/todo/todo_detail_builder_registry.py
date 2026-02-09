from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol

from app.models.todo_item import TodoItem
from app.ui.todo.todo_detail_model import DetailDocument


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
    """加载 app.ui.todo.detail_builders 下的所有模块，触发其注册行为。"""
    global _plugins_loaded
    if _plugins_loaded:
        return

    package = importlib.import_module("app.ui.todo.detail_builders")
    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        importlib.import_module(module_info.name)

    _plugins_loaded = True


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
    ensure_detail_builder_plugins_loaded()

    normalized_type = str(detail_type or "")

    direct_builder = _builders_by_type.get(normalized_type)
    if direct_builder is not None:
        return direct_builder(context, todo, info, normalized_type)

    for prefix, builder in _prefix_builders:
        if normalized_type.startswith(prefix):
            return builder(context, todo, info, normalized_type)

    for predicate, builder in _predicate_builders:
        if predicate(normalized_type, info):
            return builder(context, todo, info, normalized_type)

    if _fallback_builder is None:
        raise RuntimeError("TodoDetailBuilder registry 未注册 fallback builder")
    return _fallback_builder(context, todo, info, normalized_type)


