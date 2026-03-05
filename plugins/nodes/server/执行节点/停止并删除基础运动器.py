from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="停止并删除基础运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串"), ("是否停止所有基础运动器", "布尔值")],
    outputs=[("流程出", "流程")],
    description="停止并删除一个运行中的运动器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 停止并删除基础运动器(game, 目标实体, 运动器名称, 是否停止所有基础运动器):
    """停止并删除一个运行中的运动器"""
    ent_id = game._get_entity_id(目标实体)
    ent = game.get_entity(ent_id)
    if ent is None:
        return

    stop_motor = getattr(game, "stop_motor", None)
    if not callable(stop_motor):
        return

    if bool(是否停止所有基础运动器):
        timers = getattr(game, "timers", None)
        if isinstance(timers, dict):
            prefix = f"{ent.entity_id}___motor__"
            names: list[str] = []
            for k, info in list(timers.items()):
                if not isinstance(k, str):
                    continue
                if not k.startswith(prefix):
                    continue
                if not isinstance(info, dict):
                    continue
                if str(info.get("kind") or "") != "__motor__":
                    continue
                mname = str(info.get("motor_name") or "")
                if mname:
                    names.append(mname)
            for n in names:
                stop_motor(ent, motor_name=n, fire_stop_event=True)
        return

    name = str(运动器名称 or "").strip()
    if not name:
        return
    stop_motor(ent, motor_name=name, fire_stop_event=True)
    log_info("[停止并删除基础运动器] name={}", name)
