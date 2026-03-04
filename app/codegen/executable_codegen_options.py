from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutableCodegenOptions:
    """可执行代码生成选项（上层决定运行时导入与校验策略）。"""

    import_mode: str = "workspace_bootstrap"
    """导入模式：
    - workspace_bootstrap：在生成文件内注入 sys.path（project_root/assets；不要注入 app），再导入 `app.runtime.engine.graph_prelude_*`
    - local_prelude：兼容别名（等同 workspace_bootstrap；资源库节点图不再维护 `_prelude.py/.pyi`）
    """

    enable_auto_validate: bool = True
    """是否为生成的节点图类添加 `@validate_node_graph` 装饰器。

    说明：
    - 仅影响“生成的源码是否携带校验钩子”；
    - 当源码包含 `@validate_node_graph` 时，节点图类在被导入/定义时会触发一次性文件级校验；
      若存在 error，默认会抛出 `NodeGraphValidationError`，用于确保不支持语法/非法节点调用在运行阶段立刻暴露。
    """

    prelude_module_server: str = "app.runtime.engine.graph_prelude_server"
    prelude_module_client: str = "app.runtime.engine.graph_prelude_client"
    """workspace_bootstrap 模式下使用的 prelude 模块路径。"""

    validator_import_path: str = "engine.validate.node_graph_validator"
    """校验器模块路径（推荐使用引擎侧统一入口）。

    备注：`app.runtime.engine.node_graph_validator` 会 re-export 引擎入口，便于节点图源码通过稳定路径调用。
    """


__all__ = ["ExecutableCodegenOptions"]

