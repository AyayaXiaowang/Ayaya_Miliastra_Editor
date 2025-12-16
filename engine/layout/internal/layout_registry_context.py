from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set

from engine.configs.settings import Settings
from engine.nodes.node_registry import NodeRegistry, get_node_registry


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
    node_registry: NodeRegistry
    entity_inputs_by_name: Dict[str, Set[str]]
    variadic_min_args: Dict[str, int]

    @classmethod
    def build(cls, workspace_path: Path, *, include_composite: bool = True) -> "LayoutRegistryContext":
        if not isinstance(workspace_path, Path):
            raise TypeError("workspace_path 必须是 pathlib.Path 实例")
        resolved_workspace = workspace_path.resolve()
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


