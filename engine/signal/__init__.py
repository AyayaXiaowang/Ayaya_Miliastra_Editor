from __future__ import annotations

"""信号系统领域服务入口。

本子包集中承载与“信号定义 / 绑定 / 代码生成 / 校验协作”相关的纯引擎层逻辑，
为其他引擎子模块提供统一的领域 API，避免在各处零散地硬编码信号特例。

暴露的核心组件：
- SignalDefinitionRepository / get_default_signal_repository
- SignalBindingService / get_default_signal_binding_service
- SignalCodegenAdapter
- compute_signal_schema_hash（基于包级 signals 生成稳定的 schema 版本哈希）
"""

from .definition_repository import (  # noqa: F401
    SignalDefinitionRepository,
    get_default_signal_repository,
)
from .binding_service import (  # noqa: F401
    SignalBindingService,
    get_default_signal_binding_service,
)
from .codegen_adapter import SignalCodegenAdapter  # noqa: F401
from .schema_utils import compute_signal_schema_hash  # noqa: F401


def __getattr__(name: str):
    """延迟导入以避免与 validate 子系统形成循环依赖。

    注意：`engine.validate` 的部分规则会在 import 时访问 `engine.signal`（例如 EventNameRule），
    而 `SignalValidationSuite` 又需要引用 validate 规则类型。若在本模块顶层导入该 suite，
    会导致引擎入口（`import engine`）出现循环导入。
    """
    if name == "SignalValidationSuite":
        from .validation_suite import SignalValidationSuite

        return SignalValidationSuite
    raise AttributeError(name)

