from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import asdict
import json

from .node_definition_loader import load_all_nodes, NodeDef
from .port_type_system import BOOLEAN_TYPE_KEYWORDS
from .pipeline.runner import run_pipeline
from .pipeline.node_library import NodeLibrary
from engine.utils.logging.logger import log_info
from engine.utils.graph.node_defs_fingerprint import compute_node_defs_fingerprint
from engine.utils.cache.cache_paths import get_node_cache_dir


class NodeRegistry:
    """集中式节点注册表

    统一加载并缓存节点定义，派生并缓存各类索引，避免在不同模块中重复解析与各自实现派生逻辑。
    """

    def __init__(self, workspace_path: Path, include_composite: bool = True):
        self.workspace_path: Path = workspace_path
        self.include_composite: bool = include_composite

        self._library: Optional[Dict[str, NodeDef]] = None
        self._flow_node_names: Optional[Set[str]] = None
        self._boolean_node_names: Optional[Set[str]] = None
        self._data_query_node_names: Optional[Set[str]] = None
        self._entity_input_params_by_func: Optional[Dict[str, Set[str]]] = None
        self._variadic_min_args: Optional[Dict[str, int]] = None
        self._is_loading: bool = False  # 加载中标志，防止递归加载
        self._index_cache: Optional[Dict[str, object]] = None
        self._node_library_view: Optional[NodeLibrary] = None

    # ------------------------ 基础装载 ------------------------
    def _ensure_library(self) -> None:
        if self._library is not None:
            return
        
        # 如果正在加载中，返回空字典避免递归（防止在加载复合节点时重复触发）
        if self._is_loading:
            return
        
        self._is_loading = True
        
        # 先尝试从持久化缓存加载
        cached = self._load_persistent_node_library()
        if cached is not None:
            self._library = cached
            # 命中缓存时清理索引视图，按需懒构建
            self._index_cache = None
            self._node_library_view = None
            self._is_loading = False
            return
        
        # 未命中缓存：执行全量加载并写入缓存
        log_info(
            "[缓存][节点库] 未命中持久化缓存，开始全量扫描与解析"
            f"（workspace={self.workspace_path}，include_composite={self.include_composite}）..."
        )
        # 以工作区根目录为节点实现库根路径：
        # - 现用实现库：plugins/nodes
        # - 兼容旧结构：node_implementations（存在时仍会被扫描）
        node_defs_root = self.workspace_path
        lib = load_all_nodes(node_defs_root, include_composite=self.include_composite, verbose=False)
        log_info(f"[缓存][节点库] 解析完成，共 {len(lib)} 个节点定义，写入持久化缓存中...")
        self._library = lib
        self._save_persistent_node_library(lib)
        self._is_loading = False

    def _ensure_index(self) -> None:
        """
        懒构建基于管线的索引与 NodeLibrary 视图，用于统一的 get_by_alias/list 等查询。
        说明：索引仅对“实现侧基础节点库”构建；复合节点的检索统一通过标准键在 _library 中直接命中。
        """
        if self._index_cache is not None and self._node_library_view is not None:
            return
        # 以工作区为根运行管线（只解析不导入）
        workspace_root = self.workspace_path.resolve()
        index = run_pipeline(workspace_root)
        # 最小保障：index 结构必须是 dict
        if not isinstance(index, dict):
            raise TypeError("节点索引构建失败：pipe 产物不是字典")
        self._index_cache = index
        self._node_library_view = NodeLibrary(index=index)

    # ------------------------ 持久化缓存 ------------------------
    def _get_node_cache_dir(self) -> Path:
        # 统一通过缓存路径提供器获取节点库缓存目录，避免在各处硬编码路径片段
        return get_node_cache_dir(self.workspace_path)

    def _compute_node_defs_fingerprint(self) -> str:
        """轻量指纹：用于判断节点库是否需要重建缓存。

        组成：
        - 实现库：`plugins/nodes/`
        - 节点定义/加载核心：`engine/nodes/`
        - 图解析/生成核心：`engine/graph/`
        - 复合节点库：`assets/资源库/复合节点库/`
        """
        return compute_node_defs_fingerprint(self.workspace_path)

    def _load_persistent_node_library(self) -> Optional[Dict[str, NodeDef]]:
        """从磁盘持久化缓存加载节点库（命中且指纹一致时返回）。"""
        cache_dir = self._get_node_cache_dir()
        cache_file = cache_dir / "node_library.json"
        if not cache_file.exists():
            log_info("[缓存][节点库] 未找到持久化缓存文件（app/runtime/cache/node_cache/node_library.json），需要重建")
            return None
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "node_defs_fp" not in data or "items" not in data:
            log_info("[缓存][节点库] 缓存结构不完整，跳过使用并准备重建")
            return None
        current_fp = self._compute_node_defs_fingerprint()
        if data.get("node_defs_fp") != current_fp:
            old_fp = data.get("node_defs_fp", "<none>")
            log_info(f"[缓存][节点库] 指纹变更，缓存失效（旧: {old_fp} -> 新: {current_fp}），准备重建")
            return None
        item_count = len(data.get("items", {}))
        log_info(f"[缓存][节点库] 命中持久化缓存，共 {item_count} 项，快速恢复中...")
        raw_items: Dict[str, dict] = data["items"]
        library: Dict[str, NodeDef] = {}
        for key, item in raw_items.items():
            library[key] = NodeDef(**item)
        return library

    def _save_persistent_node_library(self, library: Dict[str, NodeDef]) -> None:
        """将当前节点库写入磁盘持久化缓存。"""
        cache_dir = self._get_node_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "node_library.json"
        fp = self._compute_node_defs_fingerprint()
        log_info(f"[缓存][节点库] 写入持久化缓存：{cache_file}（{len(library)} 项，指纹={fp}）")
        payload = {
            "node_defs_fp": fp,
            "items": {k: asdict(v) for k, v in library.items()},
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log_info("[缓存][节点库] 写入完成")

    # ------------------------ 对外API ------------------------
    def refresh(self) -> None:
        """强制重载节点库与派生索引。"""
        self._library = None
        self._flow_node_names = None
        self._boolean_node_names = None
        self._data_query_node_names = None
        self._entity_input_params_by_func = None
        self._variadic_min_args = None
        self._is_loading = False
        self._index_cache = None
        self._node_library_view = None

    def get_library(self) -> Dict[str, NodeDef]:
        self._ensure_library()
        return self._library or {}

    # ------------------------ 统一查询入口 ------------------------
    def get_node_by_key(self, key: str) -> Optional[NodeDef]:
        """
        按标准键 `类别/名称` 获取节点定义。
        """
        self._ensure_library()
        lib = self._library or {}
        return lib.get(str(key))

    def get_node_by_alias(self, category: str, name_or_alias: str) -> Optional[NodeDef]:
        """
        按别名或名称获取节点定义。
        优先使用 V2 管线的别名映射（NodeLibrary.get_by_alias），得到标准键后回到 NodeDef 库取对象；
        未命中则回退为直接在 NodeDef 库中以 `类别/名称` 键直查（兼容复合节点与别名注入）。
        """
        # 先尝试索引视图
        self._ensure_index()
        result = self._node_library_view.get_by_alias(str(category), str(name_or_alias)) if self._node_library_view else None
        if result is not None:
            mapped_key, _ = result
            return self.get_node_by_key(mapped_key)
        # 回退：库直查
        candidate_key = f"{str(category)}/{str(name_or_alias)}"
        return self.get_node_by_key(candidate_key)

    def get_node_library_index(self) -> Dict[str, object]:
        """
        返回基于管线构建的索引视图（by_key/alias_to_key）。
        仅用于高级场景；常规查询请使用 get_node_by_key / get_node_by_alias。
        """
        self._ensure_index()
        return self._index_cache or {}

    def get_node_library_view(self) -> NodeLibrary:
        """
        返回封装了索引查询的 NodeLibrary 对象。
        """
        self._ensure_index()
        if self._node_library_view is None:
            raise RuntimeError("NodeLibrary 视图尚未构建")
        return self._node_library_view

    def get_flow_node_names(self) -> Set[str]:
        if self._flow_node_names is not None:
            return self._flow_node_names
        # 基础库：使用索引派生集合
        self._ensure_index()
        base_names: Set[str] = set()
        if self._node_library_view is not None:
            base_names = self._node_library_view.get_flow_node_names()
        # 复合节点：补充扫描 _library
        self._ensure_library()
        for _, node_def in (self._library or {}).items():
            if getattr(node_def, "is_composite", False):
                has_flow = (
                    any((isinstance(t, str) and ("流程" in t)) for t in node_def.input_types.values()) or
                    any((isinstance(t, str) and ("流程" in t)) for t in node_def.output_types.values()) or
                    ("流程入" in node_def.inputs) or
                    ("流程出" in node_def.outputs)
                )
                if has_flow:
                    base_names.add(node_def.name)
        self._flow_node_names = base_names
        return base_names

    def get_boolean_node_names(self) -> Set[str]:
        if self._boolean_node_names is not None:
            return self._boolean_node_names
        # 基础库：使用索引派生集合
        self._ensure_index()
        names: Set[str] = set()
        if self._node_library_view is not None:
            names = set(self._node_library_view.get_boolean_node_names())
        # 复合节点：补充扫描 _library
        self._ensure_library()
        for _, node_def in (self._library or {}).items():
            if getattr(node_def, "is_composite", False):
                for _, port_type in node_def.output_types.items():
                    if isinstance(port_type, str) and any(k in port_type for k in BOOLEAN_TYPE_KEYWORDS):
                        names.add(node_def.name)
                        break
        self._boolean_node_names = names
        return names

    def get_data_query_node_names(self) -> Set[str]:
        if self._data_query_node_names is not None:
            return self._data_query_node_names
        self._ensure_library()
        names: Set[str] = set()
        for _, node_def in (self._library or {}).items():
            cat = getattr(node_def, "category", "") or ""
            if isinstance(cat, str) and (("查询" in cat) or ("运算" in cat)):
                names.add(node_def.name)
        self._data_query_node_names = names
        return names

    def get_entity_input_params_by_func(self) -> Dict[str, Set[str]]:
        if self._entity_input_params_by_func is not None:
            return self._entity_input_params_by_func
        self._ensure_library()
        mapping: Dict[str, Set[str]] = {}
        for _, node_def in (self._library or {}).items():
            for port_name, port_type in node_def.input_types.items():
                if isinstance(port_type, str) and ("实体" in port_type):
                    mapping.setdefault(node_def.name, set()).add(port_name)
        self._entity_input_params_by_func = mapping
        return mapping

    def get_variadic_min_args(self) -> Dict[str, int]:
        if self._variadic_min_args is not None:
            return self._variadic_min_args
        # 基础库：使用索引派生集合
        self._ensure_index()
        rules: Dict[str, int] = {}
        if self._node_library_view is not None:
            rules.update(self._node_library_view.get_variadic_min_args())
        # 复合节点：补充扫描 _library
        self._ensure_library()
        for _, node_def in (self._library or {}).items():
            if getattr(node_def, "is_composite", False):
                if not node_def.inputs:
                    continue
                variadic_inputs: List[str] = [inp for inp in node_def.inputs if "~" in inp]
                if not variadic_inputs:
                    continue
                if len(variadic_inputs) == 1:
                    rules[node_def.name] = rules.get(node_def.name, 1)
                else:
                    rules[node_def.name] = 2
        self._variadic_min_args = rules
        return rules

_registry_cache: Dict[Tuple[Path, bool], NodeRegistry] = {}


def _make_registry_key(workspace_path: Path, include_composite: bool) -> Tuple[Path, bool]:
    """构造用于区分不同工作区与复合节点配置的缓存键。"""
    return (workspace_path.resolve(), bool(include_composite))


def get_node_registry(workspace_path: Path, include_composite: bool = True) -> NodeRegistry:
    """获取指定工作区与 include_composite 组合下的 NodeRegistry 实例。

    - 不同的 (workspace_path.resolve(), include_composite) 组合拥有各自独立的注册表实例；
    - 同一组合多次调用将复用同一个实例，以避免重复扫描与指纹计算开销。
    """
    key = _make_registry_key(workspace_path, include_composite)
    if key not in _registry_cache:
        resolved_workspace = key[0]
        _registry_cache[key] = NodeRegistry(
            workspace_path=resolved_workspace,
            include_composite=include_composite,
        )
    return _registry_cache[key]


def clear_all_registries_for_tests() -> None:
    """仅供测试环境使用：清空所有已缓存的 NodeRegistry 实例。

    测试代码可以在切换 workspace_path 或 include_composite 场景前调用，
    确保不同测试用例之间不会通过 NodeRegistry 状态产生隐性耦合。
    """
    _registry_cache.clear()



