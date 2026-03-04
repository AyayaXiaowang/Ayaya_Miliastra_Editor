"""可执行/可运行 Python 代码生成器（应用层）。

说明：
- 输入为 `engine.graph.models.GraphModel`（中立产物）
- 输出为可运行的 Graph Code（类结构 Python）
- “运行时导入/插件导入/是否自动校验”由上层通过参数决定

备注：
- 该模块对外保持稳定导入路径：`app.codegen.executable_code_generator`
- 具体实现已按职责拆分到同目录下的 `executable_codegen_*.py`，以降低单文件复杂度。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from engine.graph.common import VarNameCounter, collect_input_params as collect_input_params_common
from engine.graph.models import GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.signal import SignalCodegenAdapter
from engine.utils.name_utils import sanitize_class_name

from .executable_codegen_emit_graph import _ExecutableCodegenEmitGraphMixin
from .executable_codegen_emit_node_call import _ExecutableCodegenEmitNodeCallMixin
from .executable_codegen_header import _ExecutableCodegenHeaderMixin
from .executable_codegen_node_def import _ExecutableCodegenNodeDefMixin
from .executable_codegen_options import ExecutableCodegenOptions
from .executable_codegen_runtime_exports import _ExecutableCodegenRuntimeExportsMixin
from .executable_codegen_typed_constants import _ExecutableCodegenTypedConstantsMixin
from .executable_codegen_type_inference import _ExecutableCodegenTypeInferenceMixin


class ExecutableCodeGenerator(
    _ExecutableCodegenHeaderMixin,
    _ExecutableCodegenNodeDefMixin,
    _ExecutableCodegenTypedConstantsMixin,
    _ExecutableCodegenRuntimeExportsMixin,
    _ExecutableCodegenTypeInferenceMixin,
    _ExecutableCodegenEmitGraphMixin,
    _ExecutableCodegenEmitNodeCallMixin,
):
    """可执行/可运行 Python 代码生成器（应用层）。"""

    def __init__(
        self,
        workspace_path: Path,
        node_library: Optional[Dict[str, NodeDef]] = None,
        *,
        options: Optional[ExecutableCodegenOptions] = None,
    ) -> None:
        self.workspace_path = workspace_path
        if node_library is None:
            registry = get_node_registry(workspace_path, include_composite=True)
            self.node_library = registry.get_library()
        else:
            self.node_library = node_library

        self.options = options or ExecutableCodegenOptions()
        self.var_name_counter = VarNameCounter(0)
        self._signal_codegen = SignalCodegenAdapter()
        self._current_graph_type: str = "server"
        self._runtime_exports_by_scope: Dict[str, Dict[str, Callable[..., object]]] = {}
        self._requires_game_cache: Dict[Tuple[str, str], bool] = {}

        # 事件方法内“类型化常量”复用缓存：
        # - 用于为 GUID/配置ID/元件ID/阵营 等端口生成带中文类型注解的常量变量，
        #   避免在 Graph Code 中直接内联数字导致类型不匹配；
        # - 同时允许在泛型端口（如 拼装字典）复用同一份类型化变量，帮助推断字典/列表具体类型。
        self._typed_const_cache: Dict[Tuple[str, str], str] = {}
        self._typed_const_counter: int = 0
        self._typed_const_type_by_int_value: Dict[int, str] = {}

    def generate_code(self, graph_model: GraphModel, metadata: Optional[Dict[str, Any]] = None) -> str:
        """生成可运行的节点图类结构 Python 源码。"""
        if metadata is None:
            metadata = {}

        lines: list[str] = []
        lines.extend(self._generate_executable_header(graph_model, metadata))

        graph_type = metadata.get("graph_type", "server")
        self._current_graph_type = str(graph_type or "server")
        lines.extend(self._generate_executable_imports(graph_type))

        lines.append("")
        lines.extend(self._generate_graph_variables_block(graph_model))
        lines.append("")
        lines.extend(self._generate_graph_class(graph_model))
        return "\n".join(lines)

    def _collect_input_params(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
    ) -> Dict[str, str]:
        return collect_input_params_common(node, graph_model, var_mapping)

    def _sanitize_class_name(self, name: str) -> str:
        return sanitize_class_name(name)


__all__ = [
    "ExecutableCodegenOptions",
    "ExecutableCodeGenerator",
]

