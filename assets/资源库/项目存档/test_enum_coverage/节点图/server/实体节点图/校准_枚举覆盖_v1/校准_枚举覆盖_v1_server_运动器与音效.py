"""
graph_id: server_enum_coverage_movers_and_audio_v1__test_enum_coverage
graph_name: 校准_枚举覆盖_v1_server_运动器与音效
graph_type: server
description: 枚举覆盖图（拆分版）：覆盖跟随/定点运动器与音效衰减方式、单位状态移除方式等输入枚举；每个事件 ≤ 20 节点。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(
    p
    for p in Path(__file__).resolve().parents
    if (p / "assets" / "资源库").is_dir() or ((p / "engine").is_dir() and (p / "app").is_dir())
)
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / "assets"))

from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403

GRAPH_VARIABLES: list[GraphVariableConfig] = []


class 校准_枚举覆盖_v1_server_运动器与音效:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity
        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        占位_GUID: "GUID" = "1073742001"
        占位_配置ID: "配置ID" = 1000000001
        占位_三维向量: "三维向量" = 创建三维向量(self.game, X分量=1.25, Y分量=2.50, Z分量=3.75)
        目标实体_引用: "实体" = 事件源实体
        跟随坐标系_相对: "枚举" = "相对坐标系"

        # --- 跟随运动器：覆盖 跟随坐标系 / 跟随类型 ---
        以GUID切换跟随运动器的目标(
            self.game,
            目标实体=目标实体_引用,
            跟随目标GUID=占位_GUID,
            跟随目标挂接点名称="校准_挂接点",
            位置偏移=占位_三维向量,
            旋转偏移=占位_三维向量,
            跟随坐标系="世界坐标系",
            跟随类型="完全跟随",
        )
        以GUID切换跟随运动器的目标(
            self.game,
            目标实体=目标实体_引用,
            跟随目标GUID=占位_GUID,
            跟随目标挂接点名称="校准_挂接点",
            位置偏移=占位_三维向量,
            旋转偏移=占位_三维向量,
            跟随坐标系=跟随坐标系_相对,
            跟随类型="跟随位置",
        )
        # 跟随类型候选项比坐标系更多，覆盖剩余值时会重复一次坐标系取值（不影响“枚举候选项是否出现”目的）
        以GUID切换跟随运动器的目标(
            self.game,
            目标实体=目标实体_引用,
            跟随目标GUID=占位_GUID,
            跟随目标挂接点名称="校准_挂接点",
            位置偏移=占位_三维向量,
            旋转偏移=占位_三维向量,
            跟随坐标系=跟随坐标系_相对,
            跟随类型="跟随旋转",
        )

        # --- 定点运动器：覆盖 移动方式 / 参数类型 ---
        开启定点运动器(
            self.game,
            目标实体=目标实体_引用,
            运动器名称="校准_定点运动器",
            移动方式="瞬间移动",
            移动速度=1.0,
            目标位置=占位_三维向量,
            目标旋转=占位_三维向量,
            是否锁定旋转=False,
            参数类型="固定速度",
            移动时间=1.0,
        )
        开启定点运动器(
            self.game,
            目标实体=目标实体_引用,
            运动器名称="校准_定点运动器",
            移动方式="匀速直线运动",
            移动速度=1.0,
            目标位置=占位_三维向量,
            目标旋转=占位_三维向量,
            是否锁定旋转=False,
            参数类型="固定时间",
            移动时间=1.0,
        )

        # --- 音效衰减方式（线性/先快后慢/先慢后快） ---
        添加音效播放器(
            self.game,
            目标实体=目标实体_引用,
            音效资产索引=1,
            音量=1,
            播放速度=1.0,
            是否循环播放=False,
            循环间隔时间=0.0,
            是否为3D音效=False,
            范围半径=1.0,
            衰减方式="线性衰减",
            挂接点名称="校准_挂接点",
            挂接点偏移=占位_三维向量,
        )
        添加音效播放器(
            self.game,
            目标实体=目标实体_引用,
            音效资产索引=1,
            音量=1,
            播放速度=1.0,
            是否循环播放=False,
            循环间隔时间=0.0,
            是否为3D音效=False,
            范围半径=1.0,
            衰减方式="先快后慢",
            挂接点名称="校准_挂接点",
            挂接点偏移=占位_三维向量,
        )
        添加音效播放器(
            self.game,
            目标实体=目标实体_引用,
            音效资产索引=1,
            音量=1,
            播放速度=1.0,
            是否循环播放=False,
            循环间隔时间=0.0,
            是否为3D音效=False,
            范围半径=1.0,
            衰减方式="先慢后快",
            挂接点名称="校准_挂接点",
            挂接点偏移=占位_三维向量,
        )

        # --- 移除单位状态：覆盖移除方式（2） ---
        移除单位状态(
            self.game,
            移除目标实体=目标实体_引用,
            单位状态配置ID=占位_配置ID,
            移除方式="所有同名并存状态",
            移除者实体=目标实体_引用,
        )
        移除单位状态(
            self.game,
            移除目标实体=目标实体_引用,
            单位状态配置ID=占位_配置ID,
            移除方式="最快丢失叠加层数的状态",
            移除者实体=目标实体_引用,
        )

        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))


