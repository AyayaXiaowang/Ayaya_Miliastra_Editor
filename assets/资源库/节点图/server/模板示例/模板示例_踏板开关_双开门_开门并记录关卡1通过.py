"""
graph_id: server_template_pedal_double_door_open_and_mark_level1_01
graph_name: 模板示例_踏板开关_双开门_开门并记录关卡1通过
graph_type: server
description: 监听 `通用踏板开关_状态变化` 信号；当指定踏板激活时，让双开门的左右两扇门分别向左右移动，同时播放特效1与音效1，并将玩家自定义变量“关卡1已通过”写为 True。

节点图变量：
- 踏板GUID: GUID = 0 [对外暴露]
- 左门GUID: GUID = 0 [对外暴露]
- 右门GUID: GUID = 0 [对外暴露]

- 开门位移距离: 浮点数 = 2.0 [对外暴露]
- 开门位移速度: 浮点数 = 2.0 [对外暴露]

- 开门特效配置ID: 配置ID = 1 [对外暴露]
- 开门特效挂接点: 字符串 = "Root" [对外暴露]

- 开门音效资产索引: 整数 = 1 [对外暴露]
- 开门音效音量: 整数 = 100 [对外暴露]

- 玩家通关变量名: 字符串 = "关卡1已通过" [对外暴露]

- 双开门是否已打开: 布尔值 = False

- 左门原始位置: 三维向量 = (0,0,0)
- 左门原始旋转: 三维向量 = (0,0,0)
- 右门原始位置: 三维向量 = (0,0,0)
- 右门原始旋转: 三维向量 = (0,0,0)
- 左门打开目标位置: 三维向量 = (0,0,0)
- 右门打开目标位置: 三维向量 = (0,0,0)
"""

from __future__ import annotations

import pathlib
import sys

脚本文件路径 = pathlib.Path(__file__).resolve()
节点图根目录 = 脚本文件路径.parents[2]  # 节点图根目录（.../节点图）
服务器节点图目录 = 节点图根目录 / "server"  # 包含 server 侧 `_prelude.py` 的目录
if str(服务器节点图目录) not in sys.path:
    sys.path.insert(0, str(服务器节点图目录))

from _prelude import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="踏板GUID",
        variable_type="GUID",
        default_value=0,
        description="对外暴露：触发本图的踏板实体 GUID（仅响应该踏板广播的状态变化信号）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="左门GUID",
        variable_type="GUID",
        default_value=0,
        description="对外暴露：双开门左侧门实体 GUID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="右门GUID",
        variable_type="GUID",
        default_value=0,
        description="对外暴露：双开门右侧门实体 GUID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="开门位移距离",
        variable_type="浮点数",
        default_value=2.0,
        description="对外暴露：双开门打开时，左右门沿参考右向量移动的距离（左门为负向，右门为正向）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="开门位移速度",
        variable_type="浮点数",
        default_value=2.0,
        description="对外暴露：双开门打开运动速度。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="开门特效配置ID",
        variable_type="配置ID",
        default_value=1,
        description="对外暴露：开门时播放的特效配置 ID（特效1）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="开门特效挂接点",
        variable_type="字符串",
        default_value="Root",
        description="对外暴露：开门特效挂接点名称。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="开门音效资产索引",
        variable_type="整数",
        default_value=1,
        description="对外暴露：开门时播放的音效资产索引（音效1）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="开门音效音量",
        variable_type="整数",
        default_value=100,
        description="对外暴露：开门音效音量（0~100）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="玩家通关变量名",
        variable_type="字符串",
        default_value="关卡1已通过",
        description="对外暴露：写入玩家自定义变量的变量名（示例默认写入“关卡1已通过=True”）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="双开门是否已打开",
        variable_type="布尔值",
        default_value=False,
        description="内部缓存：是否已完成开门流程，用于避免重复触发与重复写变量。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="左门原始位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部缓存：左门初始位置（在首次开门时写入，用于调试观察）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="左门原始旋转",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部缓存：左门初始旋转。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="右门原始位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部缓存：右门初始位置（在首次开门时写入，用于调试观察）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="右门原始旋转",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部缓存：右门初始旋转。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="左门打开目标位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部缓存：左门打开目标位置（首次开门时写入）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="右门打开目标位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="内部缓存：右门打开目标位置（首次开门时写入）。",
        is_exposed=False,
    ),
]


class 模板示例_踏板开关_双开门_开门并记录关卡1通过:
    """踏板激活 -> 双开门左右打开 -> 播特效/音效 -> 写玩家通关变量。

    触发源：
    - 踏板端使用 `模板示例_踏板开关_信号广播` 广播 `通用踏板开关_状态变化(是否激活)`；
    - 本图按 `踏板GUID` 白名单过滤，仅在指定踏板激活（是否激活=True）时触发开门流程。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """初始化一次性开门状态。"""
        设置节点图变量(
            self.game,
            变量名="双开门是否已打开",
            变量值=False,
            是否触发事件=False,
        )

    # ---------------------------- 事件：监听踏板状态信号 ----------------------------
    def on_通用踏板开关_状态变化(
        self,
        事件源实体,
        事件源GUID,
        信号来源实体,
        是否激活,
    ):
        """踏板激活时触发开门，并记录玩家通关变量。"""
        是否激活_布尔值: "布尔值" = 是否激活
        if 是否激活_布尔值:
            pass
        else:
            return

        双开门是否已打开: "布尔值" = 获取节点图变量(
            self.game,
            变量名="双开门是否已打开",
        )
        if 双开门是否已打开:
            return

        踏板GUID: "GUID" = 获取节点图变量(
            self.game,
            变量名="踏板GUID",
        )
        来源GUID: "GUID" = 以实体查询GUID(
            self.game,
            实体=信号来源实体,
        )
        是否指定踏板: "布尔值" = 是否相等(
            self.game,
            输入1=来源GUID,
            输入2=踏板GUID,
        )
        if 是否指定踏板:
            pass
        else:
            return

        # 一次性开门：先写入“已打开”，避免并发信号导致重复触发
        设置节点图变量(
            self.game,
            变量名="双开门是否已打开",
            变量值=True,
            是否触发事件=False,
        )

        左门GUID: "GUID" = 获取节点图变量(
            self.game,
            变量名="左门GUID",
        )
        右门GUID: "GUID" = 获取节点图变量(
            self.game,
            变量名="右门GUID",
        )
        左门实体: "实体" = 以GUID查询实体(self.game, GUID=左门GUID)
        右门实体: "实体" = 以GUID查询实体(self.game, GUID=右门GUID)

        左门原始位置, 左门原始旋转 = 获取实体位置与旋转(
            self.game,
            目标实体=左门实体,
        )
        右门原始位置, 右门原始旋转 = 获取实体位置与旋转(
            self.game,
            目标实体=右门实体,
        )
        左门原始位置: "三维向量"
        左门原始旋转: "三维向量"
        右门原始位置: "三维向量"
        右门原始旋转: "三维向量"

        设置节点图变量(
            self.game,
            变量名="左门原始位置",
            变量值=左门原始位置,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="左门原始旋转",
            变量值=左门原始旋转,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="右门原始位置",
            变量值=右门原始位置,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="右门原始旋转",
            变量值=右门原始旋转,
            是否触发事件=False,
        )

        开门位移距离: "浮点数" = 获取节点图变量(
            self.game,
            变量名="开门位移距离",
        )
        开门位移速度: "浮点数" = 获取节点图变量(
            self.game,
            变量名="开门位移速度",
        )

        # 使用左门的本地右向量作为参考方向：左门向负向移动，右门向正向移动
        参考右向量: "三维向量" = 获取实体向右向量(
            self.game,
            目标实体=左门实体,
        )
        负向位移距离: "浮点数" = 减法运算(
            self.game,
            左值=0.0,
            右值=开门位移距离,
        )
        左门位移向量: "三维向量" = 三维向量缩放(
            self.game,
            三维向量=参考右向量,
            缩放倍率=负向位移距离,
        )
        右门位移向量: "三维向量" = 三维向量缩放(
            self.game,
            三维向量=参考右向量,
            缩放倍率=开门位移距离,
        )

        左门打开目标位置: "三维向量" = 三维向量加法(
            self.game,
            三维向量1=左门原始位置,
            三维向量2=左门位移向量,
        )
        右门打开目标位置: "三维向量" = 三维向量加法(
            self.game,
            三维向量1=右门原始位置,
            三维向量2=右门位移向量,
        )
        设置节点图变量(
            self.game,
            变量名="左门打开目标位置",
            变量值=左门打开目标位置,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="右门打开目标位置",
            变量值=右门打开目标位置,
            是否触发事件=False,
        )

        停止并删除基础运动器(
            self.game,
            目标实体=左门实体,
            运动器名称="双开门_左门定点运动",
            是否停止所有基础运动器=False,
        )
        开启定点运动器(
            self.game,
            目标实体=左门实体,
            运动器名称="双开门_左门定点运动",
            移动方式="匀速直线运动",
            移动速度=开门位移速度,
            目标位置=左门打开目标位置,
            目标旋转=左门原始旋转,
            是否锁定旋转=True,
            参数类型="固定速度",
            移动时间=0.0,
        )

        停止并删除基础运动器(
            self.game,
            目标实体=右门实体,
            运动器名称="双开门_右门定点运动",
            是否停止所有基础运动器=False,
        )
        开启定点运动器(
            self.game,
            目标实体=右门实体,
            运动器名称="双开门_右门定点运动",
            移动方式="匀速直线运动",
            移动速度=开门位移速度,
            目标位置=右门打开目标位置,
            目标旋转=右门原始旋转,
            是否锁定旋转=True,
            参数类型="固定速度",
            移动时间=0.0,
        )

        # 开门特效：默认分别在左右门的 Root 挂接点播放同一特效配置（特效1）
        开门特效配置ID: "配置ID" = 获取节点图变量(
            self.game,
            变量名="开门特效配置ID",
        )
        开门特效挂接点: "字符串" = 获取节点图变量(
            self.game,
            变量名="开门特效挂接点",
        )
        播放限时特效(
            self.game,
            特效资产=开门特效配置ID,
            目标实体=左门实体,
            挂接点名称=开门特效挂接点,
            是否跟随目标运动=True,
            是否跟随目标旋转=True,
            位置偏移=(0.0, 0.0, 0.0),
            旋转偏移=(0.0, 0.0, 0.0),
            缩放倍率=1.0,
            是否播放自带的音效=False,
        )
        播放限时特效(
            self.game,
            特效资产=开门特效配置ID,
            目标实体=右门实体,
            挂接点名称=开门特效挂接点,
            是否跟随目标运动=True,
            是否跟随目标旋转=True,
            位置偏移=(0.0, 0.0, 0.0),
            旋转偏移=(0.0, 0.0, 0.0),
            缩放倍率=1.0,
            是否播放自带的音效=False,
        )

        # 音效与通关变量：对所有在场玩家写入一次
        开门音效资产索引: "整数" = 获取节点图变量(
            self.game,
            变量名="开门音效资产索引",
        )
        开门音效音量: "整数" = 获取节点图变量(
            self.game,
            变量名="开门音效音量",
        )
        玩家通关变量名: "字符串" = 获取节点图变量(
            self.game,
            变量名="玩家通关变量名",
        )
        在场玩家实体列表: "实体列表" = 获取在场玩家实体列表(self.game)
        for 玩家实体 in 在场玩家实体列表:
            玩家播放单次2D音效(
                self.game,
                目标实体=玩家实体,
                音效资产索引=开门音效资产索引,
                音量=开门音效音量,
                播放速度=1.0,
            )
            设置自定义变量(
                self.game,
                目标实体=玩家实体,
                变量名=玩家通关变量名,
                变量值=True,
                是否触发事件=False,
            )

        # 回发确认：让一次性踏板可锁定按下并禁用触发器
        发送信号(
            self.game,
            信号名="通用踏板开关_激活确认",
            开关GUID=来源GUID,
            是否允许锁定=True,
        )

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "通用踏板开关_状态变化",
            self.on_通用踏板开关_状态变化,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file

    自身文件路径 = pathlib.Path(__file__).resolve()
    是否通过, 错误列表, 警告列表 = validate_file(自身文件路径)
    print("=" * 80)
    print(f"节点图自检: {自身文件路径.name}")
    print(f"文件: {自身文件路径}")
    if 是否通过:
        print("结果: 通过")
    else:
        print(f"结果: 未通过（错误: {len(错误列表)}，警告: {len(警告列表)}）")
        if 错误列表:
            print("\n错误明细:")
            for 序号, 错误文本 in enumerate(错误列表, start=1):
                print(f"  [{序号}] {错误文本}")
        if 警告列表:
            print("\n警告明细:")
            for 序号, 警告文本 in enumerate(警告列表, start=1):
                print(f"  [{序号}] {警告文本}")
    print("=" * 80)
    if not 是否通过:
        sys.exit(1)


