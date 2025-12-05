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
from .validation_suite import SignalValidationSuite  # noqa: F401
from .schema_utils import compute_signal_schema_hash  # noqa: F401


