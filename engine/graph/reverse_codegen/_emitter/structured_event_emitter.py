from __future__ import annotations

from engine.graph.reverse_codegen._emitter.core import _StructuredEventEmitterCore
from engine.graph.reverse_codegen._emitter.data_emitter import _StructuredEventEmitterDataEmitter
from engine.graph.reverse_codegen._emitter.flow_emitter import _StructuredEventEmitterFlowEmitter
from engine.graph.reverse_codegen._emitter.flow_handlers import _StructuredEventEmitterFlowHandlers


class _StructuredEventEmitter(
    _StructuredEventEmitterFlowHandlers,
    _StructuredEventEmitterFlowEmitter,
    _StructuredEventEmitterDataEmitter,
    _StructuredEventEmitterCore,
):
    """按流程边结构化生成事件方法体（支持 if/match/for/break + 复合节点多流程出口 match）。"""

