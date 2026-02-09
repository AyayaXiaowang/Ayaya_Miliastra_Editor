from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, TYPE_CHECKING, Any

from engine.configs.settings import Settings

if TYPE_CHECKING:
    from engine.nodes.node_registry import NodeRegistry


@dataclass(frozen=True)
class LayoutRegistryContext:
    """
    布局层对“节点注册表派生信息”的只读依赖封装。

    设计目标：
    - 彻底移除布局层对 workspace_root 的隐式回退与全局可变缓存；
    - 由调用方（LayoutService / UI / 工具脚本）显式注入 workspace_path，
      或从 settings 的单一真源（Settings.set_config_path 注入的 workspace_root）派生 workspace_path；
    - 统一承载与 UI 精确一致的高度估算/端口行规划所需的派生索引。
    """

    workspace_path: Path
    node_registry: Optional["NodeRegistry"]
    entity_inputs_by_name: Dict[str, Set[str]]
    variadic_min_args: Dict[str, int]

    @classmethod
    def build(cls, workspace_path: Path, *, include_composite: bool = True) -> "LayoutRegistryContext":
        if not isinstance(workspace_path, Path):
            raise TypeError("workspace_path 必须是 pathlib.Path 实例")
        resolved_workspace = workspace_path.resolve()
        from engine.nodes.node_registry import get_node_registry

        registry = get_node_registry(resolved_workspace, include_composite=include_composite)
        entity_inputs_by_name = registry.get_entity_input_params_by_func()
        variadic_min_args = registry.get_variadic_min_args()
        return cls(
            workspace_path=resolved_workspace,
            node_registry=registry,
            entity_inputs_by_name=entity_inputs_by_name,
            variadic_min_args=variadic_min_args,
        )

    @classmethod
    def build_from_node_library(
        cls,
        workspace_path: Path,
        *,
        node_library: Dict[str, Any],
    ) -> "LayoutRegistryContext":
        """
        基于调用方提供的节点库派生布局所需的最小索引，避免在“节点库构建中”反向触发 NodeRegistry。

        说明：
        - 该构造器不会调用 get_node_registry / NodeRegistry.get_library；
        - node_library 采用 duck-typing：只要求每个 item 具备 name/input_types/inputs 等字段（与 NodeDef 对齐）。
        """
        if not isinstance(workspace_path, Path):
            raise TypeError("workspace_path 必须是 pathlib.Path 实例")
        resolved_workspace = workspace_path.resolve()

        derived_entity_inputs: Dict[str, Set[str]] = {}
        derived_variadic_min_args: Dict[str, int] = {}

        for _, node_def in dict(node_library or {}).items():
            node_name = str(getattr(node_def, "name", "") or "")
            if node_name == "":
                continue

            input_types = getattr(node_def, "input_types", None) or {}
            if isinstance(input_types, dict):
                for port_name, port_type in input_types.items():
                    port_type_text = str(port_type or "")
                    # 实体/结构体：仅允许连线，不提供行内常量输入控件（UI/布局共用该集合）
                    if ("实体" in port_type_text) or port_type_text.startswith("结构体"):
                        derived_entity_inputs.setdefault(node_name, set()).add(str(port_name))
                        # 端口别名也应计入（旧图仍可能使用历史端口名）
                        aliases_map = getattr(node_def, "input_port_aliases", {}) or {}
                        if isinstance(aliases_map, dict):
                            aliases = aliases_map.get(str(port_name)) or []
                            if isinstance(aliases, list):
                                for alias in aliases:
                                    if isinstance(alias, str) and alias:
                                        derived_entity_inputs.setdefault(node_name, set()).add(str(alias))

            inputs = getattr(node_def, "inputs", None) or []
            if isinstance(inputs, list) and inputs:
                variadic_inputs = [str(input_name) for input_name in inputs if "~" in str(input_name)]
                if variadic_inputs:
                    derived_variadic_min_args[node_name] = 1 if len(variadic_inputs) == 1 else 2

        return cls(
            workspace_path=resolved_workspace,
            node_registry=None,
            entity_inputs_by_name=derived_entity_inputs,
            variadic_min_args=derived_variadic_min_args,
        )

    @classmethod
    def from_settings(cls, *, include_composite: bool = True) -> "LayoutRegistryContext":
        """
        从 settings 的单一真源派生 workspace_root（Settings.set_config_path(workspace_root) 注入的路径）。

        注意：若 settings 未初始化（未调用 Settings.set_config_path），将直接抛错，
        以避免任何“按文件位置猜 root”的隐式回退。
        """
        workspace_root = getattr(Settings, "_workspace_root", None)
        if isinstance(workspace_root, Path):
            return cls.build(workspace_root, include_composite=include_composite)

        raise RuntimeError(
            "无法从 settings 推导 workspace_path：Settings._workspace_root 未设置。"
            "请在启动/测试入口调用 settings.set_config_path(workspace_path)，"
            "或在调用 LayoutService.compute_layout 时显式传入 workspace_path。"
        )


def ensure_layout_registry_context_for_model(
    model: object,
    *,
    registry_context: Optional[LayoutRegistryContext] = None,
    workspace_path: Optional[Path] = None,
    include_composite: bool = True,
) -> LayoutRegistryContext:
    """
    为任意 GraphModel-like 对象确保存在可复用的 LayoutRegistryContext。

    约定缓存字段名：model._layout_registry_context_cache
    """
    cached = getattr(model, "_layout_registry_context_cache", None)
    if isinstance(registry_context, LayoutRegistryContext):
        effective = registry_context
    elif isinstance(cached, LayoutRegistryContext):
        effective = cached
    elif isinstance(workspace_path, Path):
        effective = LayoutRegistryContext.build(workspace_path, include_composite=include_composite)
    else:
        effective = LayoutRegistryContext.from_settings(include_composite=include_composite)

    setattr(model, "_layout_registry_context_cache", effective)
    return effective


