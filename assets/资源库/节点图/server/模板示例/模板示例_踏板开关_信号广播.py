"""
graph_id: server_template_pedal_switch_signal_broadcast_01
graph_name: 模板示例_踏板开关_信号广播
graph_type: server
description: 在踏板机关的完整流程中，使用信号广播“是否激活”状态替代逐个修改目标实体自定义变量的写法；接收端通过监听事件自带的“信号来源实体”识别发送方；支持最小触发人数与相对位移方向配置，并通过接收端回发确认信号实现一次性锁定。

节点图变量：
- 位移距离: 浮点数 = 1.0 [对外暴露]
- 位移速度: 浮点数 = 2.0 [对外暴露]
- 是否一次性: 布尔值 = False [对外暴露]
- 最小触发人数: 整数 = 1 [对外暴露]
- 触发器序号: 整数 = 0 [对外暴露]
- 按下特效配置ID: 配置ID = 0 [对外暴露]
- 按下特效挂接点: 字符串 = "Root" [对外暴露]
- 相对位移方向: 三维向量 = (0,-1,0) [对外暴露]

- 原始位置: 三维向量 = (0,0,0)
- 原始旋转: 三维向量 = (0,0,0)
- 按下目标位置: 三维向量 = (0,0,0)
- 运动目标状态: 字符串 = "空"
- 调试_最近一次广播_是否激活: 布尔值 = False
- 是否锁定按下: 布尔值 = False
"""

from __future__ import annotations

import sys
import pathlib

脚本文件路径 = pathlib.Path(__file__).resolve()
节点图根目录 = 脚本文件路径.parents[2]  # 节点图根目录（.../节点图）
服务器节点图目录 = 节点图根目录 / "server"  # 包含 server 侧 `_prelude.py` 的目录
if str(服务器节点图目录) not in sys.path:
    sys.path.insert(0, str(服务器节点图目录))

from _prelude import *
from engine.graph.models.package_model import GraphVariableConfig


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="位移距离",
        variable_type="浮点数",
        default_value=1.0,
        description="对外暴露：踏板按下时沿本地轴移动的距离。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="位移速度",
        variable_type="浮点数",
        default_value=2.0,
        description="对外暴露：踏板按下/回弹时的运动速度。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="是否一次性",
        variable_type="布尔值",
        default_value=False,
        description="对外暴露：是否为一次性踏板（是否锁定由接收端回发确认信号触发，而非踏板端自行决定）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="最小触发人数",
        variable_type="整数",
        default_value=1,
        description="对外暴露：需要多少个人（实体）同时处于碰撞触发器内，才开始触发按下流程。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="触发器序号",
        variable_type="整数",
        default_value=0,
        description="对外暴露：对应碰撞触发器的序号，仅在该序号被占用/清空时触发逻辑。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="按下特效配置ID",
        variable_type="配置ID",
        default_value=0,
        description="对外暴露：踏板按下完成时播放的特效配置 ID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="按下特效挂接点",
        variable_type="字符串",
        default_value="Root",
        description="对外暴露：按下特效挂接点名称。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="相对位移方向",
        variable_type="三维向量",
        default_value=(0.0, -1.0, 0.0),
        description="对外暴露：踏板按下时的相对位移方向（三维向量，使用踏板自身局部坐标系）。默认 (0,-1,0) 表示相对向下。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="原始位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="记录踏板初始位置。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="原始旋转",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="记录踏板初始旋转。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="按下目标位置",
        variable_type="三维向量",
        default_value=(0.0, 0.0, 0.0),
        description="踏板按下后的目标位置。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="运动目标状态",
        variable_type="字符串",
        default_value="空",
        description="记录当前预期的运动完成状态：空/按下/回弹。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="调试_最近一次广播_是否激活",
        variable_type="布尔值",
        default_value=False,
        description="调试用：在编辑器中镜像最近一次对外广播的“是否激活”布尔值（True=按下完成广播开启，False=回弹开始广播关闭）。不参与业务逻辑判断。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="是否锁定按下",
        variable_type="布尔值",
        default_value=False,
        description="一次性锁定状态：接收端回发确认后，若踏板配置为一次性则锁定按下并禁用触发器，不再回弹。",
        is_exposed=False,
    ),
]


class 模板示例_踏板开关_信号广播:
    """演示一个自包含的踏板机关：在按下完成和回弹开始时用信号广播“是否激活”状态。

    设计要点：
    - 在【实体创建时】缓存原始位置/旋转，并基于【位移距离】预计算按下目标位置；
    - 在【进入碰撞触发器时】检测从 0→1 的首次占用，设置目标状态为"按下"并启动定点运动器；
    - 在【离开碰撞触发器时】检测占用清空（计数归零），设置目标状态为"回弹"，立即广播“关闭”信号，并启动回弹运动；
    - 在【基础运动器停止时】根据“运动目标状态”判断是否视为“激活”，仅在按下完成时广播一次“开启”信号。
    接收方只需在自己的图中监听 `通用踏板开关_状态变化` 信号：
    - 通过监听事件自带的 `信号来源实体` 识别是哪块踏板在广播；
    - 通过参数 `是否激活` 获取踏板当前状态；
    - 若需要做“多踏板联动”，接收端可自行维护目标踏板 GUID 列表，并用 `以实体查询GUID(信号来源实体)` 进行过滤与聚合。
    """

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 事件：实体创建时 ----------------------------
    def on_实体创建时(self, 事件源实体, 事件源GUID):
        """实体创建时：缓存原始位置/旋转，预计算按下目标位置，并广播初始化信号。"""
        自身实体: "实体" = 获取自身实体(self.game)
        原始位置, 原始旋转 = 获取实体位置与旋转(
            self.game,
            目标实体=自身实体,
        )
        原始位置: "三维向量"
        原始旋转: "三维向量"

        设置节点图变量(
            self.game,
            变量名="原始位置",
            变量值=原始位置,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="原始旋转",
            变量值=原始旋转,
            是否触发事件=False,
        )

        位移距离: "浮点数" = 获取节点图变量(
            self.game,  
            变量名="位移距离",
        )
        相对位移方向: "三维向量" = 获取节点图变量(
            self.game,
            变量名="相对位移方向",
        )
        方向X: "浮点数"
        方向Y: "浮点数"
        方向Z: "浮点数"
        方向X, 方向Y, 方向Z = 拆分三维向量(
            self.game,
            三维向量=相对位移方向,
        )

        本地右向量: "三维向量" = 获取实体向右向量(self.game, 目标实体=自身实体)
        本地上向量: "三维向量" = 获取实体向上向量(self.game, 目标实体=自身实体)
        本地前向量: "三维向量" = 获取实体向前向量(self.game, 目标实体=自身实体)

        右分量向量: "三维向量" = 三维向量缩放(self.game, 三维向量=本地右向量, 缩放倍率=方向X)
        上分量向量: "三维向量" = 三维向量缩放(self.game, 三维向量=本地上向量, 缩放倍率=方向Y)
        前分量向量: "三维向量" = 三维向量缩放(self.game, 三维向量=本地前向量, 缩放倍率=方向Z)

        右上合成: "三维向量" = 三维向量加法(self.game, 三维向量1=右分量向量, 三维向量2=上分量向量)
        下沉方向向量: "三维向量" = 三维向量加法(self.game, 三维向量1=右上合成, 三维向量2=前分量向量)

        位移向量: "三维向量" = 三维向量缩放(
            self.game,
            三维向量=下沉方向向量,
            缩放倍率=位移距离,
        )
        目标位置: "三维向量" = 三维向量加法(
            self.game,
            三维向量1=原始位置,
            三维向量2=位移向量,
        )
        设置节点图变量(
            self.game,
            变量名="按下目标位置",
            变量值=目标位置,
            是否触发事件=False,
        )

        设置节点图变量(
            self.game,
            变量名="运动目标状态",
            变量值="空",
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="调试_最近一次广播_是否激活",
            变量值=False,
            是否触发事件=False,
        )
        设置节点图变量(
            self.game,
            变量名="是否锁定按下",
            变量值=False,
            是否触发事件=False,
        )

    # ---------------------------- 事件：进入碰撞触发器时 ----------------------------
    def on_进入碰撞触发器时(self, 进入者实体, 进入者实体GUID, 触发器实体, 触发器实体GUID, 触发器序号):
        """进入碰撞触发器时：满足最小触发人数且当前未处于“按下目标状态”时，启动按下运动。"""
        目标序号: "整数" = 获取节点图变量(
            self.game,
            变量名="触发器序号",
        )
        if 是否相等(
            self.game,
            枚举1=触发器序号,
            枚举2=目标序号,
        ):
            当前目标状态_进入: "字符串" = 获取节点图变量(
                self.game,
                变量名="运动目标状态",
            )
            是否已处于按下状态_进入: "布尔值" = 是否相等(
                self.game,
                枚举1=当前目标状态_进入,
                枚举2="按下",
            )
            # 已经在“按下”（包含正在下落/已到位）时，后续进入无需再触发，也无需再计算人数
            if 是否已处于按下状态_进入:
                return

            实体列表_进入 = 获取碰撞触发器内所有实体(
                self.game,
                目标实体=获取自身实体(self.game),
                触发器序号=目标序号,
            )
            当前数量_进入 = 获取列表长度(
                列表=实体列表_进入,
            )
            最小触发人数: "整数" = 获取节点图变量(
                self.game,
                变量名="最小触发人数",
            )
            是否达到触发人数: "布尔值" = 数值大于等于(
                self.game,
                左值=当前数量_进入,
                右值=最小触发人数,
            )
            # 上方已对“是否已处于按下状态”做过早退保护，这里无需再做取反/逻辑与组合
            if 是否达到触发人数:
                目标位置_进入: "三维向量" = 获取节点图变量(
                    self.game,
                    变量名="按下目标位置",
                )
                原始旋转_进入: "三维向量" = 获取节点图变量(
                    self.game,
                    变量名="原始旋转",
                )
                速度_进入: "浮点数" = 获取节点图变量(
                    self.game,
                    变量名="位移速度",
                )

                设置节点图变量(
                    self.game,
                    变量名="运动目标状态",
                    变量值="按下",
                    是否触发事件=False,
                )

                自身实体_进入: "实体" = 获取自身实体(self.game)
                # 可能存在回弹未结束就再次触发按下的情况：先停止回弹/按下运动器，避免同名停止事件误判
                停止并删除基础运动器(
                    self.game,
                    目标实体=自身实体_进入,
                    运动器名称="踏板回弹定点运动",
                    是否停止所有基础运动器=False,
                )
                停止并删除基础运动器(
                    self.game,
                    目标实体=自身实体_进入,
                    运动器名称="踏板按下定点运动",
                    是否停止所有基础运动器=False,
                )
                开启定点运动器(
                    self.game,
                    目标实体=自身实体_进入,
                    运动器名称="踏板按下定点运动",
                    移动方式="匀速直线运动",
                    移动速度=速度_进入,
                    目标位置=目标位置_进入,
                    目标旋转=原始旋转_进入,
                    是否锁定旋转=True,
                    参数类型="固定速度",
                    移动时间=0.0,
                )

                # 注意：不在此处立即广播开关状态信号，而是等到运动完成时统一广播

    # ---------------------------- 事件：离开碰撞触发器时 ----------------------------
    def on_离开碰撞触发器时(self, 离开者实体, 离开者实体GUID, 触发器实体, 触发器实体GUID, 触发器序号):
        """离开碰撞触发器时：人数不足且当前处于“按下目标状态”时，启动回弹运动。"""
        目标序号: "整数" = 获取节点图变量(
            self.game,
            变量名="触发器序号",
        )
        if 是否相等(
            self.game,
            枚举1=触发器序号,
            枚举2=目标序号,
        ):
            实体列表_离开 = 获取碰撞触发器内所有实体(
                self.game,
                目标实体=获取自身实体(self.game),
                触发器序号=目标序号,
            )
            当前数量_离开 = 获取列表长度(
                列表=实体列表_离开,
            )
            最小触发人数_离开: "整数" = 获取节点图变量(
                self.game,
                变量名="最小触发人数",
            )
            是否锁定按下: "布尔值" = 获取节点图变量(
                self.game,
                变量名="是否锁定按下",
            )
            if 是否锁定按下:
                return

            当前目标状态_离开: "字符串" = 获取节点图变量(
                self.game,
                变量名="运动目标状态",
            )
            是否处于按下状态_离开: "布尔值" = 是否相等(
                self.game,
                枚举1=当前目标状态_离开,
                枚举2="按下",
            )
            是否人数不足: "布尔值" = 数值小于(
                self.game,
                左值=当前数量_离开,
                右值=最小触发人数_离开,
            )
            if 是否处于按下状态_离开:
                if 是否人数不足:
                    原始位置_离开: "三维向量" = 获取节点图变量(
                        self.game,
                        变量名="原始位置",
                    )
                    原始旋转_离开: "三维向量" = 获取节点图变量(
                        self.game,
                        变量名="原始旋转",
                    )
                    速度_离开: "浮点数" = 获取节点图变量(
                        self.game,
                        变量名="位移速度",
                    )

                    设置节点图变量(
                        self.game,
                        变量名="运动目标状态",
                        变量值="回弹",
                        是否触发事件=False,
                    )
                    发送信号(
                        self.game,
                        信号名="通用踏板开关_状态变化",
                        是否激活=False,
                    )

                    自身实体_离开: "实体" = 获取自身实体(self.game)
                    停止并删除基础运动器(
                        self.game,
                        目标实体=自身实体_离开,
                        运动器名称="踏板按下定点运动",
                        是否停止所有基础运动器=False,
                    )
                    停止并删除基础运动器(
                        self.game,
                        目标实体=自身实体_离开,
                        运动器名称="踏板回弹定点运动",
                        是否停止所有基础运动器=False,
                    )
                    开启定点运动器(
                        self.game,
                        目标实体=自身实体_离开,
                        运动器名称="踏板回弹定点运动",
                        移动方式="匀速直线运动",
                        移动速度=速度_离开,
                        目标位置=原始位置_离开,
                        目标旋转=原始旋转_离开,
                        是否锁定旋转=True,
                        参数类型="固定速度",
                        移动时间=0.0,
                    )

    # ---------------------------- 事件：基础运动器停止时 ----------------------------
    def on_基础运动器停止时(self, 事件源实体, 事件源GUID, 运动器名称):
        """基础运动器停止时：根据目标状态广播信号。"""
        锚点实体: "实体" = 获取自身实体(self.game)

        match 运动器名称:
            case "踏板按下定点运动":
                当前目标状态: "字符串" = 获取节点图变量(
                    self.game,
                    变量名="运动目标状态",
                )
                是否激活: "布尔值" = 是否相等(
                    self.game,
                    枚举1=当前目标状态,
                    枚举2="按下",
                )

                # 写入调试变量，便于在编辑器中观察最近一次广播的状态
                设置节点图变量(
                    self.game,
                    变量名="调试_最近一次广播_是否激活",
                    变量值=是否激活,
                    是否触发事件=False,
                )

                # 若为按下完成阶段：播放特效并处理一次性逻辑
                if 是否激活:
                    按下特效配置ID_完成: "配置ID" = 获取节点图变量(
                        self.game,
                        变量名="按下特效配置ID",
                    )
                    按下特效挂接点_完成: "字符串" = 获取节点图变量(
                        self.game,
                        变量名="按下特效挂接点",
                    )
                    播放限时特效(
                        self.game,
                        特效资产=按下特效配置ID_完成,
                        目标实体=锚点实体,
                        挂接点名称=按下特效挂接点_完成,
                        是否跟随目标运动=True,
                        是否跟随目标旋转=True,
                        位置偏移=(0.0, 0.0, 0.0),
                        旋转偏移=(0.0, 0.0, 0.0),
                        缩放倍率=1.0,
                        是否播放自带的音效=False,
                    )

                # 使用示例信号广播踏板状态：订阅者只需监听该信号即可执行自身逻辑
                if 是否激活:
                    发送信号(
                        self.game,
                        信号名="通用踏板开关_状态变化",
                        是否激活=True,
                    )
            case "踏板回弹定点运动":
                return
            case _:
                return

    # ---------------------------- 事件：监听接收端回发确认 ----------------------------
    def on_通用踏板开关_激活确认(
        self,
        事件源实体,
        事件源GUID,
        信号来源实体,
        开关GUID,
        是否允许锁定,
    ):
        """接收端在完成联动目标（如开门）后回发确认：一次性踏板据此锁定并禁用触发器，不再回弹。"""
        自身实体: "实体" = 获取自身实体(self.game)
        自身GUID: "GUID" = 以实体查询GUID(
            self.game,
            实体=自身实体,
        )
        是否给本踏板: "布尔值" = 是否相等(
            self.game,
            枚举1=开关GUID,
            枚举2=自身GUID,
        )
        是否允许锁定_布尔: "布尔值" = 是否允许锁定
        是否一次性: "布尔值" = 获取节点图变量(
            self.game,
            变量名="是否一次性",
        )

        # 使用正向条件串联双分支：只在“是”分支继续向下连线，未满足条件则不做任何事直接结束
        if 是否给本踏板:
            if 是否允许锁定_布尔:
                if 是否一次性:
                    # 标记锁定，阻止后续离开触发器时启动回弹
                    设置节点图变量(
                        self.game,
                        变量名="是否锁定按下",
                        变量值=True,
                        是否触发事件=False,
                    )

                    # 禁用触发器，作为“一次性”的最终生效动作（由接收端回发信号触发）
                    目标序号_禁用: "整数" = 获取节点图变量(
                        self.game,
                        变量名="触发器序号",
                    )
                    激活关闭碰撞触发器(
                        self.game,
                        目标实体=获取自身实体(self.game),
                        触发器序号=目标序号_禁用,
                        是否激活=False,
                    )

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "进入碰撞触发器时",
            self.on_进入碰撞触发器时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "离开碰撞触发器时",
            self.on_离开碰撞触发器时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "基础运动器停止时",
            self.on_基础运动器停止时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "通用踏板开关_激活确认",
            self.on_通用踏板开关_激活确认,
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



