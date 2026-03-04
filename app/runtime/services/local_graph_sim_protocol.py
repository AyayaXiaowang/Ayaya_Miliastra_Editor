from __future__ import annotations

"""
Local Graph Sim 的前后端协议定义（单一真源）。

目标：
- 统一 API 路径常量，避免 Python/JS 多处硬编码；
- 所有 JSON 响应都带 schema_version/protocol_version，字段改动可被监控页与 pytest 及时发现；
- 提供 /api/local_sim/protocol 端点，前端可自描述加载协议。
"""

from dataclasses import dataclass


LOCAL_SIM_PROTOCOL_VERSION = 1
LOCAL_SIM_SCHEMA_VERSION = 1

LOCAL_SIM_API_BASE = "/api/local_sim"


@dataclass(frozen=True, slots=True)
class LocalSimApiRoutes:
    base: str = LOCAL_SIM_API_BASE

    # status / info
    status: str = f"{LOCAL_SIM_API_BASE}/status"
    protocol: str = f"{LOCAL_SIM_API_BASE}/protocol"
    entities: str = f"{LOCAL_SIM_API_BASE}/entities"
    trace: str = f"{LOCAL_SIM_API_BASE}/trace"
    last_action: str = f"{LOCAL_SIM_API_BASE}/last_action"
    snapshot: str = f"{LOCAL_SIM_API_BASE}/snapshot"
    validation_status: str = f"{LOCAL_SIM_API_BASE}/validation_status"

    # patches / runtime sync
    bootstrap: str = f"{LOCAL_SIM_API_BASE}/bootstrap"
    sync: str = f"{LOCAL_SIM_API_BASE}/sync"
    poll: str = f"{LOCAL_SIM_API_BASE}/poll"

    # actions
    click: str = f"{LOCAL_SIM_API_BASE}/click"
    emit_signal: str = f"{LOCAL_SIM_API_BASE}/emit_signal"
    resolve_ui_key: str = f"{LOCAL_SIM_API_BASE}/resolve_ui_key"
    validate: str = f"{LOCAL_SIM_API_BASE}/validate"
    restart: str = f"{LOCAL_SIM_API_BASE}/restart"
    clear_trace: str = f"{LOCAL_SIM_API_BASE}/clear_trace"
    export_repro: str = f"{LOCAL_SIM_API_BASE}/export_repro"

    # time control
    pause: str = f"{LOCAL_SIM_API_BASE}/pause"
    pause_status: str = f"{LOCAL_SIM_API_BASE}/pause_status"
    step: str = f"{LOCAL_SIM_API_BASE}/step"


LOCAL_SIM_API = LocalSimApiRoutes()


def build_local_sim_protocol_payload() -> dict:
    """
    协议自描述 payload（GET /api/local_sim/protocol）。

    说明：
    - protocol_version：协议整体版本（路由、返回结构的“兼容性约束”）
    - schema_version：所有 JSON 响应通用的 schema 版本
    """
    api = LOCAL_SIM_API
    return {
        "ok": True,
        "protocol_version": int(LOCAL_SIM_PROTOCOL_VERSION),
        "schema_version": int(LOCAL_SIM_SCHEMA_VERSION),
        "api_base": str(api.base),
        "endpoints": {
            "status": str(api.status),
            "protocol": str(api.protocol),
            "entities": str(api.entities),
            "trace": str(api.trace),
            "last_action": str(api.last_action),
            "snapshot": str(api.snapshot),
            "validation_status": str(api.validation_status),
            "bootstrap": str(api.bootstrap),
            "sync": str(api.sync),
            "poll": str(api.poll),
            "click": str(api.click),
            "emit_signal": str(api.emit_signal),
            "resolve_ui_key": str(api.resolve_ui_key),
            "validate": str(api.validate),
            "restart": str(api.restart),
            "clear_trace": str(api.clear_trace),
            "export_repro": str(api.export_repro),
            "pause": str(api.pause),
            "pause_status": str(api.pause_status),
            "step": str(api.step),
        },
        "notes": {
            "status": "监控页会话信息与当前 UI/layout",
            "poll": "推进虚拟时间（未暂停）+ drain patches + 回传 bindings.lv",
            "sync": "一次性回传当前 UI 状态（layout/groups/widget_states）",
            "protocol": "协议自描述；前端可用它消除硬编码",
        },
    }


__all__ = [
    "LOCAL_SIM_PROTOCOL_VERSION",
    "LOCAL_SIM_SCHEMA_VERSION",
    "LOCAL_SIM_API_BASE",
    "LOCAL_SIM_API",
    "LocalSimApiRoutes",
    "build_local_sim_protocol_payload",
]

