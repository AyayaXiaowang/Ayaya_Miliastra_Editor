"""节点图编辑器流程服务与会话状态机。

说明：
- 本包用于将 GraphEditorController 的跨域链路拆成可组合、可定位的流程服务；
- 控制器仅负责信号转发与依赖注入，不在此处写 UI 级 Qt 信号。
"""

from .session_state_machine import GraphEditorSessionStateMachine
from .load_service import GraphEditorLoadService, GraphEditorLoadRequest, GraphEditorLoadResult
from .save_service import GraphEditorSaveService, GraphEditorSaveResult
from .validate_service import GraphEditorValidateService
from .auto_layout_prepare_service import GraphEditorAutoLayoutPrepareService
from .auto_layout_reparse_thread import GraphAutoLayoutReparseResult, GraphAutoLayoutReparseThread
from .graph_prepare_thread import GraphPrepareResult, GraphPrepareThread
from .new_node_ports_policy import derive_initial_input_names_for_new_node

__all__ = [
    "GraphEditorSessionStateMachine",
    "GraphEditorLoadService",
    "GraphEditorLoadRequest",
    "GraphEditorLoadResult",
    "GraphEditorSaveService",
    "GraphEditorSaveResult",
    "GraphEditorValidateService",
    "GraphEditorAutoLayoutPrepareService",
    "GraphAutoLayoutReparseResult",
    "GraphAutoLayoutReparseThread",
    "GraphPrepareResult",
    "GraphPrepareThread",
    "derive_initial_input_names_for_new_node",
]


