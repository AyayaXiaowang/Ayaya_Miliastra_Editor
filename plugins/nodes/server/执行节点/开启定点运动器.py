from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info
import math

@node_spec(
    name="开启定点运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串"), ("移动方式", "枚举"), ("移动速度", "浮点数"), ("目标位置", "三维向量"), ("目标旋转", "三维向量"), ("是否锁定旋转", "布尔值"), ("参数类型", "枚举"), ("移动时间", "浮点数")],
    outputs=[("流程出", "流程")],
    description="在关卡运行时为目标实体动态添加一个定点运动型基础运动器",
    doc_reference="服务器节点/执行节点/执行节点.md",
    input_enum_options={
        "移动方式": ["瞬间移动", "匀速直线运动"],
        "参数类型": ["固定速度", "固定时间"],
    },
)
def 开启定点运动器(game, 目标实体, 运动器名称, 移动方式, 移动速度, 目标位置, 目标旋转, 是否锁定旋转, 参数类型, 移动时间):
    """在关卡运行时为目标实体动态添加一个定点运动型基础运动器"""
    # 离线模拟约定：基础运动器停止事件不应在“开启运动器”的同一事件栈内同步触发，
    # 否则容易与 `第七关_开始游戏` 等初始化信号形成重入（在数据服务尚未写入关键变量前就推进后续流程）。
    # 因此对 duration<=0 的运动统一最小延迟到下一次 tick（一个极小的正数）。
    MIN_DURATION = 0.0001

    name = str(运动器名称 or "").strip()
    if not name:
        raise ValueError("运动器名称不能为空")

    move_type = str(移动方式 or "").strip()
    param_type = str(参数类型 or "").strip()

    ent_id = game._get_entity_id(目标实体)
    ent = game.get_entity(ent_id)
    if ent is None:
        raise ValueError(f"目标实体不存在: {ent_id!r}")

    target_pos = list(目标位置) if isinstance(目标位置, (list, tuple)) else [0.0, 0.0, 0.0]
    target_rot = list(目标旋转) if isinstance(目标旋转, (list, tuple)) else list(getattr(ent, "rotation", [0.0, 0.0, 0.0]))
    lock_rot = bool(是否锁定旋转)

    # 瞬移：直接写回位姿，但停止事件延迟到下一次 tick
    if move_type == "瞬间移动":
        ent.position = [float(target_pos[0]), float(target_pos[1]), float(target_pos[2])]
        if lock_rot and len(target_rot) == 3:
            ent.rotation = [float(target_rot[0]), float(target_rot[1]), float(target_rot[2])]
        duration = float(MIN_DURATION)
    else:
        # 计算持续时间
        duration: float
        if param_type == "固定时间":
            duration = float(移动时间)
            if duration < 0:
                raise ValueError(f"移动时间必须 >= 0: {移动时间!r}")
        else:
            speed = float(移动速度)
            if speed <= 0:
                raise ValueError(f"移动速度必须 > 0: {移动速度!r}")
            cur = getattr(ent, "position", [0.0, 0.0, 0.0])
            dx = float(target_pos[0]) - float(cur[0])
            dy = float(target_pos[1]) - float(cur[1])
            dz = float(target_pos[2]) - float(cur[2])
            dist = float(math.sqrt(dx * dx + dy * dy + dz * dz))
            duration = float(dist / speed) if dist > 0 else 0.0

    if duration <= 0:
        duration = float(MIN_DURATION)

    start_motor = getattr(game, "start_motor", None)
    if not callable(start_motor):
        raise RuntimeError("MockRuntime 缺少 start_motor，无法离线模拟基础运动器")
    start_motor(
        ent,
        motor_name=name,
        duration=float(duration),
        target_position=[float(target_pos[0]), float(target_pos[1]), float(target_pos[2])],
        target_rotation=[float(target_rot[0]), float(target_rot[1]), float(target_rot[2])],
        lock_rotation=bool(lock_rot),
    )
    log_info("[开启定点运动器] name={} duration={}", name, float(duration))
