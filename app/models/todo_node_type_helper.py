"""节点类型推断辅助 - 用于判断节点是否需要类型设置"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Dict, List, Literal, Optional, Set

from engine.nodes.node_registry import get_node_registry
from engine.utils.cache.cache_paths import get_node_cache_dir
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.nodes.port_name_rules import get_dynamic_port_type


@dataclass(frozen=True)
class DynamicPortBehavior:
    mode: Literal["variadic_inputs", "key_value_pairs", "flow_branch_outputs"]


@dataclass(frozen=True)
class DynamicPortPlan(DynamicPortBehavior):
    add_count: int
    port_tokens: tuple[str, ...] = ()


class NodeTypeHelper:
    """节点类型推断辅助类
    
    负责判断节点是否包含泛型端口，以及获取需要设置类型的端口列表。
    """
    
    _GLOBAL_LIBRARY_CACHE: Dict[str, Dict[str, Any]] = {}
    _GLOBAL_NAME_INDEX_CACHE: Dict[str, Dict[str, Any]] = {}
    _GLOBAL_LIBRARY_SIGNATURES: Dict[str, float] = {}
    _GLOBAL_VARIADIC_RULES_CACHE: Dict[str, Dict[str, int]] = {}
    _ALPHA_NUMERIC_SUFFIX_PATTERN = re.compile(r"^(?P<prefix>[^\d]+)(?P<index>\d+)$")

    def __init__(self, workspace_path: Optional[Path] = None):
        """初始化类型辅助器
        
        Args:
            workspace_path: 工作区路径，用于加载节点库
        """
        if workspace_path is not None and not isinstance(workspace_path, Path):
            workspace_path = Path(workspace_path)
        self.workspace_path = workspace_path
        self._node_library: Optional[Dict[str, Any]] = None
        self._name_to_node_def: Dict[str, Any] = {}
        self._variadic_rules: Dict[str, int] = {}
    
    def get_node_library(self) -> Dict[str, Any]:
        """获取节点库（懒加载）
        
        Returns:
            节点库字典，键为节点定义名，值为节点定义对象
        """
        if self._node_library is not None:
            return self._node_library
        
        workspace_path = self._resolve_workspace_root()
        cache_key = self._resolve_cache_key(workspace_path)

        signature = self._compute_library_signature(workspace_path)
        cached_library = self._GLOBAL_LIBRARY_CACHE.get(cache_key)
        cached_signature = self._GLOBAL_LIBRARY_SIGNATURES.get(cache_key)
        if cached_library is not None and cached_signature == signature:
            self._node_library = cached_library
            cached_name_index = self._GLOBAL_NAME_INDEX_CACHE.get(cache_key)
            self._name_to_node_def = cached_name_index if cached_name_index is not None else {}
            cached_variadic_rules = self._GLOBAL_VARIADIC_RULES_CACHE.get(cache_key)
            self._variadic_rules = cached_variadic_rules if cached_variadic_rules is not None else {}
            return self._node_library
        
        registry = get_node_registry(workspace_path, include_composite=True)
        self._node_library = registry.get_library()
        
        # 构建按名称的索引映射（O(1) 查找）
        self._name_to_node_def = {}
        for node_def in self._node_library.values():
            node_name = getattr(node_def, "name", None)
            if node_name:
                self._name_to_node_def[node_name] = node_def
        
        self._GLOBAL_LIBRARY_CACHE[cache_key] = self._node_library
        self._GLOBAL_NAME_INDEX_CACHE[cache_key] = self._name_to_node_def
        self._GLOBAL_LIBRARY_SIGNATURES[cache_key] = signature
        variadic_rules = registry.get_variadic_min_args()
        self._variadic_rules = variadic_rules
        self._GLOBAL_VARIADIC_RULES_CACHE[cache_key] = variadic_rules
        
        return self._node_library

    def _resolve_workspace_root(self) -> Path:
        if self.workspace_path:
            return Path(self.workspace_path).resolve()
        return Path(__file__).resolve().parent.parent.parent

    def _resolve_cache_key(self, workspace_path: Path) -> str:
        return str(workspace_path)
    
    def has_generic_ports_for_node(self, node_obj) -> bool:
        """判断节点是否包含任何"泛型"端口（输入或输出，含复合类型如"泛型列表/字典"）。
        
        Args:
            node_obj: 节点对象（需包含 title 属性）
            
        Returns:
            如果节点包含泛型端口则返回 True，否则返回 False
        """
        self.get_node_library()
        node_name = getattr(node_obj, "title", "") or ""
        
        # 使用索引进行 O(1) 查找
        node_def = self._name_to_node_def.get(node_name)
        if node_def:
            # 输入/输出任一侧包含"泛型"即认为需要类型设置
            in_has = any(
                (isinstance(t, str) and ("泛型" in t)) 
                for t in getattr(node_def, "input_types", {}).values()
            )
            out_has = any(
                (isinstance(t, str) and ("泛型" in t)) 
                for t in getattr(node_def, "output_types", {}).values()
            )
            dyn_has = (
                isinstance(getattr(node_def, "dynamic_port_type", ""), str) 
                and ("泛型" in getattr(node_def, "dynamic_port_type", ""))
            )
            return bool(in_has or out_has or dyn_has)
        
        return False
    
    def list_generic_input_ports(self, node_obj) -> List[str]:
        """返回节点的所有"泛型"输入端口名（排除流程口）。
        
        Args:
            node_obj: 节点对象（需包含 title 属性）
            
        Returns:
            泛型输入端口名列表
        """
        self.get_node_library()
        node_name = getattr(node_obj, "title", "") or ""
        node_def = self._name_to_node_def.get(node_name)
        if not node_def:
            return []

        input_types: Dict[str, str] = dict(getattr(node_def, "input_types", {}) or {})
        dynamic_type = str(getattr(node_def, "dynamic_port_type", "") or "")

        has_generic_decl = any(
            isinstance(t, str) and ("泛型" in t) for t in input_types.values()
        )
        if (not has_generic_decl) and (not (dynamic_type and "泛型" in dynamic_type)):
            return []

        generic_names: List[str] = []
        for port in getattr(node_obj, "inputs", []) or []:
            port_name = getattr(port, "name", "") or ""
            if not isinstance(port_name, str) or port_name == "":
                continue
            if is_flow_port_name(port_name):
                continue

            declared_type = ""
            if port_name in input_types:
                declared_type = str(input_types.get(port_name, "") or "")
            else:
                declared_type = get_dynamic_port_type(
                    str(port_name), dict(input_types), dynamic_type
                ) or ""

            if isinstance(declared_type, str) and ("泛型" in declared_type):
                generic_names.append(port_name)

        return generic_names

    def list_generic_output_ports(self, node_obj) -> List[str]:
        """返回节点的所有"泛型"输出端口名（排除流程口）。
        
        Args:
            node_obj: 节点对象（需包含 title 属性）
            
        Returns:
            泛型输出端口名列表
        """
        self.get_node_library()
        node_name = getattr(node_obj, "title", "") or ""
        node_def = self._name_to_node_def.get(node_name)
        if not node_def:
            return []

        output_types: Dict[str, str] = dict(getattr(node_def, "output_types", {}) or {})
        dynamic_type = str(getattr(node_def, "dynamic_port_type", "") or "")

        has_generic_decl = any(
            isinstance(t, str) and ("泛型" in t) for t in output_types.values()
        )
        if (not has_generic_decl) and (not (dynamic_type and "泛型" in dynamic_type)):
            return []

        generic_names: List[str] = []
        for port in getattr(node_obj, "outputs", []) or []:
            port_name = getattr(port, "name", "") or ""
            if not isinstance(port_name, str) or port_name == "":
                continue
            if is_flow_port_name(port_name):
                continue

            declared_type = ""
            if port_name in output_types:
                declared_type = str(output_types.get(port_name, "") or "")
            else:
                declared_type = get_dynamic_port_type(
                    str(port_name), dict(output_types), dynamic_type
                ) or ""

            if isinstance(declared_type, str) and ("泛型" in declared_type):
                generic_names.append(port_name)

        return generic_names

    def get_node_def_for_model(self, node_obj) -> Optional[Any]:
        """根据节点模型对象获取对应的节点定义。
        
        Args:
            node_obj: 节点模型对象（需包含 title 属性）
            
        Returns:
            对应的节点定义对象，若不存在则返回 None
        """
        self.get_node_library()
        node_name = getattr(node_obj, "title", "") or ""
        if not node_name:
            return None
        return self._name_to_node_def.get(node_name)

    def describe_dynamic_port_behavior(self, node_obj) -> Optional[DynamicPortBehavior]:
        """保留旧接口，返回无需计数的动态端口类型。"""
        plan = self.plan_dynamic_ports(node_obj)
        if plan is None:
            return None
        return DynamicPortBehavior(mode=plan.mode)

    def plan_dynamic_ports(self, node_obj) -> Optional[DynamicPortPlan]:
        """结合节点定义与命名模式，返回需要新增端口的执行计划。"""
        from engine.graph.common import SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE

        self.get_node_library()
        node_name = getattr(node_obj, "title", "") or ""
        if not node_name:
            return None
        # 信号节点的端口形状由信号定义驱动，不通过“新增动态端口”步骤管理
        if node_name in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
            return None
        node_def = self._name_to_node_def.get(node_name)
        if not node_def:
            return None

        dynamic_port_type = str(getattr(node_def, "dynamic_port_type", "") or "")
        if dynamic_port_type == "流程":
            tokens = tuple(self._collect_branch_output_names(node_obj))
            add_count = len(tokens)
            if add_count <= 0:
                return None
            return DynamicPortPlan(mode="flow_branch_outputs", add_count=add_count, port_tokens=tokens)

        if node_name not in self._variadic_rules:
            return None

        if self._node_has_key_value_variadic_inputs(node_obj):
            indices = self._collect_key_value_pair_indices(node_obj)
            add_count = len(indices) - 1 if len(indices) > 1 else 0
            if add_count <= 0:
                return None
            return DynamicPortPlan(mode="key_value_pairs", add_count=add_count, port_tokens=tuple(str(i) for i in sorted(indices)))
        if self._node_has_numeric_variadic_inputs(node_obj):
            numeric_inputs = self._collect_numeric_input_names(node_obj)
            add_count = len(numeric_inputs) - 1 if len(numeric_inputs) > 1 else 0
            if add_count <= 0:
                return None
            return DynamicPortPlan(mode="variadic_inputs", add_count=add_count, port_tokens=tuple(numeric_inputs))
        return None

    @classmethod
    def invalidate_cache(cls, workspace_path: Optional[Path] = None) -> None:
        """显式清除缓存，便于在节点库被外部刷新后重建索引。"""
        if workspace_path is None:
            cls._GLOBAL_LIBRARY_CACHE.clear()
            cls._GLOBAL_NAME_INDEX_CACHE.clear()
            cls._GLOBAL_LIBRARY_SIGNATURES.clear()
            cls._GLOBAL_VARIADIC_RULES_CACHE.clear()
            return
        normalized = str(Path(workspace_path).resolve())
        cls._GLOBAL_LIBRARY_CACHE.pop(normalized, None)
        cls._GLOBAL_NAME_INDEX_CACHE.pop(normalized, None)
        cls._GLOBAL_LIBRARY_SIGNATURES.pop(normalized, None)
        cls._GLOBAL_VARIADIC_RULES_CACHE.pop(normalized, None)

    def _collect_numeric_input_names(self, node_obj) -> List[str]:
        results: List[str] = []
        for port in getattr(node_obj, "inputs", []):
            name = getattr(port, "name", "")
            if isinstance(name, str) and name.isdigit():
                results.append(name)
        return results

    def _node_has_numeric_variadic_inputs(self, node_obj) -> bool:
        return bool(self._collect_numeric_input_names(node_obj))

    def _node_has_key_value_variadic_inputs(self, node_obj) -> bool:
        return bool(self._collect_key_value_pair_indices(node_obj))

    def _collect_key_value_pair_indices(self, node_obj) -> Set[int]:
        indices_by_prefix: Dict[str, Set[int]] = {}
        for port in getattr(node_obj, "inputs", []):
            name = str(getattr(port, "name", "") or "")
            prefix, index = self._split_alpha_numeric_suffix(name)
            if prefix and index is not None:
                indices_by_prefix.setdefault(prefix, set()).add(index)
        if len(indices_by_prefix) < 2:
            return set()
        sorted_groups = sorted(indices_by_prefix.values(), key=lambda values: len(values), reverse=True)
        if len(sorted_groups) < 2:
            return set()
        primary = sorted_groups[0]
        secondary = sorted_groups[1]
        return primary & secondary

    def _split_alpha_numeric_suffix(self, name: str) -> tuple[str, Optional[int]]:
        match = self._ALPHA_NUMERIC_SUFFIX_PATTERN.match(name)
        if not match:
            return "", None
        prefix = match.group("prefix")
        index = match.group("index")
        return prefix, int(index)

    def _collect_branch_output_names(self, node_obj) -> List[str]:
        outputs: List[str] = []
        for port in getattr(node_obj, "outputs", []):
            name = getattr(port, "name", "") or ""
            if not isinstance(name, str):
                continue
            normalized = name.strip()
            if normalized and normalized != "默认":
                outputs.append(normalized)
        return outputs

    def _compute_library_signature(self, workspace_path: Path) -> float:
        cache_dir = get_node_cache_dir(workspace_path)
        cache_file = cache_dir / "node_library.json"
        if cache_file.exists():
            return cache_file.stat().st_mtime
        return 0.0

