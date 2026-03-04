from __future__ import annotations

import ast
from pathlib import Path
import tokenize
from typing import Dict, Tuple

from engine.graph.utils.ast_utils import (
    NOT_EXTRACTABLE,
    clear_module_constants_context,
    collect_module_constants,
    extract_constant_value,
    set_module_constants_context,
)
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir
from engine.utils.workspace import (
    get_injected_workspace_root_or_none,
    looks_like_workspace_root,
    resolve_workspace_root,
)


def _find_module_assignment_value(tree: ast.Module, name: str) -> ast.expr | None:
    """在模块顶层寻找对 name 的赋值表达式节点（支持 Assign/AnnAssign）。"""
    want = str(name or "").strip()
    if not want:
        return None

    for stmt in list(getattr(tree, "body", []) or []):
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            for target in targets:
                if isinstance(target, ast.Name) and target.id == want:
                    return stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            if isinstance(target, ast.Name) and target.id == want:
                return getattr(stmt, "value", None)

    return None


def _try_extract_id_and_payload_from_code(
    py_path: Path,
    *,
    id_name: str,
    payload_name: str,
) -> tuple[str | None, dict | None]:
    """从代码级资源文件中静态提取 (ID, PAYLOAD)。

    约定：该方法**不执行**模块顶层代码；仅支持静态可提取的常量赋值：
    - `<ID_NAME> = "..."`
    - `<PAYLOAD_NAME> = { ... }`
    - payload 内允许引用同模块内已声明的常量（例如 `SIGNAL_ID`）。
    """
    if not py_path.is_file():
        return None, None

    with tokenize.open(str(py_path)) as f:
        source_text = f.read()

    tree = ast.parse(source_text, filename=str(py_path))
    constants = collect_module_constants(tree)
    set_module_constants_context(constants)

    id_expr = _find_module_assignment_value(tree, str(id_name))
    if id_expr is None:
        clear_module_constants_context()
        return None, None
    id_value = extract_constant_value(id_expr)
    if id_value is NOT_EXTRACTABLE or not isinstance(id_value, str) or not id_value:
        clear_module_constants_context()
        return None, None

    payload_expr = _find_module_assignment_value(tree, str(payload_name))
    if payload_expr is None:
        clear_module_constants_context()
        return None, None
    payload_value = extract_constant_value(payload_expr)
    clear_module_constants_context()

    if payload_value is NOT_EXTRACTABLE or not isinstance(payload_value, dict):
        return None, None
    return str(id_value), dict(payload_value)


class CodeSchemaResourceService:
    """结构体 / 信号的代码级 Schema 载入服务（基于 assets 代码资源）。

    设计目标：
    - 为结构体与信号提供统一、只读的 {id: payload} 视图；
    - 隔离具体数据来源（当前从代码资源目录动态加载，必要时可在外部封装缓存）；
    - 不在导入阶段访问 ResourceManager，避免循环依赖。
    """

    def _get_workspace_root(self) -> Path:
        injected_root = get_injected_workspace_root_or_none()
        if injected_root is not None and looks_like_workspace_root(injected_root):
            return injected_root
        return resolve_workspace_root(start_paths=[Path(__file__).resolve()])

    def _get_schema_resource_roots(self, *, active_package_id: str | None) -> list[Path]:
        """按作用域返回需要参与 Schema 聚合的资源根目录列表。

        设计约定（与 ResourceIndexBuilder/ResourceManager 一致）：
        - active_package_id=None：仅共享根（避免混入其它项目存档，且允许跨存档重复 ID）；
        - active_package_id=str：共享根 + 指定项目存档根（项目存档可覆盖共享同 ID 定义）。
        """
        workspace = self._get_workspace_root()
        resource_library_root = workspace / "assets" / "资源库"

        roots: list[Path] = []
        shared_root = get_shared_root_dir(resource_library_root)
        if shared_root.exists() and shared_root.is_dir():
            roots.append(shared_root)

        normalized = str(active_package_id or "").strip()
        # UI 特殊视图 ID：不绑定任何项目存档，只扫描共享根目录
        if normalized in {"global_view", "unclassified_view"}:
            normalized = ""

        if normalized:
            package_root = get_packages_root_dir(resource_library_root) / normalized
            if package_root.exists() and package_root.is_dir():
                roots.append(package_root)

        return roots

    def _load_struct_definitions_from_code(
        self,
        *,
        active_package_id: str | None = None,
    ) -> Tuple[Dict[str, Dict], Dict[str, Path]]:
        """从 assets 代码资源中加载结构体定义。

        约定：
        - 根目录：assets/资源库/<资源根目录>/管理配置/结构体定义
          - 共享根：assets/资源库/共享/...
          - 项目存档根：assets/资源库/项目存档/<package_id>/...
        - 子目录：按需分组的子文件夹（可选），例如 basic/、ingame_save/ 等
        - 每个 .py 文件导出：
          - STRUCT_ID: str
          - STRUCT_PAYLOAD: dict
        """
        resource_roots = self._get_schema_resource_roots(active_package_id=active_package_id)
        base_dirs = [root / "管理配置" / "结构体定义" for root in resource_roots]

        results: Dict[str, Dict] = {}
        sources: Dict[str, Path] = {}

        for base_dir in base_dirs:
            if not base_dir.is_dir():
                continue

            seen_in_root: Dict[str, Path] = {}
            py_paths = sorted(
                (path for path in base_dir.rglob("*.py") if path.is_file()),
                key=lambda path: path.as_posix(),
            )
            for py_path in py_paths:
                # 允许在目录中放置校验或工具脚本（如 `校验结构体定义.py`），这些脚本不参与 Schema 聚合。
                if "校验" in py_path.stem:
                    continue
                struct_id_value, payload_value = _try_extract_id_and_payload_from_code(
                    py_path,
                    id_name="STRUCT_ID",
                    payload_name="STRUCT_PAYLOAD",
                )

                # 代码级资源文件若不符合约定（缺少 STRUCT_ID/STRUCT_PAYLOAD），
                # 不应阻断编辑器启动；跳过该文件并让校验阶段提示修复。
                if struct_id_value is None or payload_value is None:
                    continue

                struct_id = str(struct_id_value)
                if struct_id in seen_in_root:
                    previous = seen_in_root.get(struct_id)
                    # 同一资源根目录内重复 ID：视为错误，但不在此处抛错阻断启动。
                    # 保持稳定行为：py_paths 已排序，保留先出现的那一份。
                    _ = previous
                    continue
                seen_in_root[struct_id] = py_path

                # 跨根覆盖语义：项目存档根允许覆盖共享根的同 ID 定义，避免歧义。
                results[struct_id] = dict(payload_value)
                sources[struct_id] = py_path

        return results, sources

    def _load_signal_definitions_from_code(
        self,
        *,
        active_package_id: str | None = None,
    ) -> Tuple[Dict[str, Dict], Dict[str, Path]]:
        """从 assets 代码资源中加载信号定义。

        约定：
        - 根目录：assets/资源库/<资源根目录>/管理配置/信号
        - 每个 .py 文件导出：
          - SIGNAL_ID: str
          - SIGNAL_PAYLOAD: dict
        """
        resource_roots = self._get_schema_resource_roots(active_package_id=active_package_id)
        base_dirs = [root / "管理配置" / "信号" for root in resource_roots]

        results: Dict[str, Dict] = {}
        sources: Dict[str, Path] = {}

        for base_dir in base_dirs:
            if not base_dir.is_dir():
                continue

            seen_in_root: Dict[str, Path] = {}
            py_paths = sorted(
                (path for path in base_dir.rglob("*.py") if path.is_file()),
                key=lambda path: path.as_posix(),
            )
            for py_path in py_paths:
                # 允许在目录中放置校验或工具脚本（如 `校验信号.py`），这些脚本不参与 Schema 聚合。
                if "校验" in py_path.stem:
                    continue
                signal_id_value, payload_value = _try_extract_id_and_payload_from_code(
                    py_path,
                    id_name="SIGNAL_ID",
                    payload_name="SIGNAL_PAYLOAD",
                )

                # 代码级资源文件若不符合约定（缺少 SIGNAL_ID/SIGNAL_PAYLOAD），
                # 不应阻断编辑器启动；跳过该文件并让校验阶段提示修复。
                if signal_id_value is None or payload_value is None:
                    continue

                signal_id = str(signal_id_value)
                if signal_id in seen_in_root:
                    previous = seen_in_root.get(signal_id)
                    # 同一资源根目录内重复 ID：视为错误，但不在此处抛错阻断启动。
                    # 保持稳定行为：py_paths 已排序，保留先出现的那一份。
                    _ = previous
                    continue
                seen_in_root[signal_id] = py_path

                # 跨根覆盖语义：项目存档根允许覆盖共享根的同 ID 定义，避免歧义。
                results[signal_id] = dict(payload_value)
                sources[signal_id] = py_path

        return results, sources

    def load_all_struct_definitions(self, *, active_package_id: str | None = None) -> Dict[str, Dict]:
        """加载所有结构体定义，返回 {struct_id: payload}。

        仅从 assets 代码资源加载；若目录中没有任何结构体定义，则返回空字典。
        """
        definitions, _sources = self._load_struct_definitions_from_code(active_package_id=active_package_id)
        return definitions

    def load_all_struct_definitions_with_sources(
        self,
        *,
        active_package_id: str | None = None,
    ) -> Tuple[Dict[str, Dict], Dict[str, Path]]:
        """加载所有结构体定义，并返回其来源文件路径映射。

        Returns:
            (definitions, sources)
            - definitions: {struct_id: payload}
            - sources: {struct_id: absolute_path_to_py}
        """
        return self._load_struct_definitions_from_code(active_package_id=active_package_id)

    def load_all_signal_definitions(self, *, active_package_id: str | None = None) -> Dict[str, Dict]:
        """加载所有信号定义，返回 {signal_id: payload}。

        仅从 assets 代码资源加载；若目录中没有任何信号定义，则返回空字典。
        """
        definitions, _sources = self._load_signal_definitions_from_code(active_package_id=active_package_id)
        return definitions

    def load_all_signal_definitions_with_sources(
        self,
        *,
        active_package_id: str | None = None,
    ) -> Tuple[Dict[str, Dict], Dict[str, Path]]:
        """加载所有信号定义，并返回其来源文件路径映射。

        Returns:
            (definitions, sources)
            - definitions: {signal_id: payload}
            - sources: {signal_id: absolute_path_to_py}
        """
        return self._load_signal_definitions_from_code(active_package_id=active_package_id)


class DefinitionSchemaView:
    """结构体 / 信号 Schema 聚合视图（进程内缓存，只读）。"""

    def __init__(self, schema_service: CodeSchemaResourceService | None = None) -> None:
        self._schema_service = schema_service or CodeSchemaResourceService()
        # 当前作用域：None 表示仅共享根；str 表示共享根 + 指定项目存档根。
        self._active_package_id: str | None = None
        self._struct_definitions: Dict[str, Dict] | None = None
        self._signal_definitions: Dict[str, Dict] | None = None
        self._struct_definition_sources: Dict[str, Path] | None = None
        self._signal_definition_sources: Dict[str, Path] | None = None

    def set_active_package_id(self, package_id: str | None) -> None:
        """设置 Schema 视图的项目存档作用域。

        约定：
        - None / "global_view" / "unclassified_view"：仅共享根；
        - 其它非空字符串：共享根 + 指定项目存档根。

        说明：作用域变化会使缓存失效，下次访问时会重新加载。
        """
        normalized = str(package_id or "").strip()
        if normalized in {"global_view", "unclassified_view"}:
            normalized = ""
        normalized_or_none: str | None = normalized or None
        if normalized_or_none == self._active_package_id:
            return
        self._active_package_id = normalized_or_none
        self.invalidate_all_caches()

    def get_all_struct_definitions(self) -> Dict[str, Dict]:
        """返回 {struct_id: payload}，payload 为结构体定义原始字典的副本。"""
        if self._struct_definitions is None:
            definitions, sources = self._schema_service.load_all_struct_definitions_with_sources(
                active_package_id=self._active_package_id
            )
            self._struct_definitions = definitions
            self._struct_definition_sources = sources
        return self._struct_definitions

    def get_all_signal_definitions(self) -> Dict[str, Dict]:
        """返回 {signal_id: payload}，payload 为信号定义原始字典的副本。"""
        if self._signal_definitions is None:
            definitions, sources = self._schema_service.load_all_signal_definitions_with_sources(
                active_package_id=self._active_package_id
            )
            self._signal_definitions = definitions
            self._signal_definition_sources = sources
        return self._signal_definitions

    def get_all_struct_definition_sources(self) -> Dict[str, Path]:
        """返回 {struct_id: absolute_path_to_py}。

        注意：该映射用于校验/诊断定位结构体定义的来源位置，调用方不应修改返回值。
        """
        # 确保 definitions + sources 已同时加载
        _ = self.get_all_struct_definitions()
        if self._struct_definition_sources is None:
            return {}
        return dict(self._struct_definition_sources)

    def get_all_signal_definition_sources(self) -> Dict[str, Path]:
        """返回 {signal_id: absolute_path_to_py}。

        注意：该映射用于校验/诊断定位信号定义的来源位置，调用方不应修改返回值。
        """
        _ = self.get_all_signal_definitions()
        if self._signal_definition_sources is None:
            return {}
        return dict(self._signal_definition_sources)

    def invalidate_struct_cache(self) -> None:
        """使结构体定义缓存失效，下次调用 get_all_struct_definitions 时重新加载。"""
        self._struct_definitions = None
        self._struct_definition_sources = None

    def invalidate_signal_cache(self) -> None:
        """使信号定义缓存失效，下次调用 get_all_signal_definitions 时重新加载。"""
        self._signal_definitions = None
        self._signal_definition_sources = None

    def invalidate_all_caches(self) -> None:
        """使所有缓存失效。"""
        self._struct_definitions = None
        self._signal_definitions = None
        self._struct_definition_sources = None
        self._signal_definition_sources = None


_default_schema_view: DefinitionSchemaView | None = None


def get_default_definition_schema_view() -> DefinitionSchemaView:
    """获取进程级默认 DefinitionSchemaView 实例（带缓存）。"""
    global _default_schema_view
    if _default_schema_view is None:
        _default_schema_view = DefinitionSchemaView()
    return _default_schema_view


def set_default_definition_schema_view_active_package_id(package_id: str | None) -> None:
    """同步默认 SchemaView 的作用域（共享根 / 共享+当前存档）。"""
    schema_view = get_default_definition_schema_view()
    set_active = getattr(schema_view, "set_active_package_id", None)
    if callable(set_active):
        set_active(package_id)


def invalidate_default_struct_cache() -> None:
    """使默认 Schema 视图的结构体缓存失效。
    
    当结构体定义文件发生变化时调用此函数，
    下次访问 get_all_struct_definitions() 时会重新加载。
    """
    global _default_schema_view
    if _default_schema_view is not None:
        _default_schema_view.invalidate_struct_cache()


def invalidate_default_signal_cache() -> None:
    """使默认 Schema 视图的信号缓存失效。
    
    当信号定义文件发生变化时调用此函数，
    下次访问 get_all_signal_definitions() 时会重新加载。
    """
    global _default_schema_view
    if _default_schema_view is not None:
        _default_schema_view.invalidate_signal_cache()


def invalidate_all_default_schema_caches() -> None:
    """使默认 Schema 视图的所有缓存失效。"""
    global _default_schema_view
    if _default_schema_view is not None:
        _default_schema_view.invalidate_all_caches()


