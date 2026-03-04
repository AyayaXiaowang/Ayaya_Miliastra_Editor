"""
graph_id: server_test_project_level7_ingame_global_controller
graph_name: 关卡实体_第七关_UI游戏中_公共控制
graph_type: server
description: 第七关“游戏中”公共控制图（关卡实体单实例）：

- 接管全局信号监听：关卡大厅_开始关卡 / 第七关_开始游戏 / 第七关_下发本局纸条 / 第七关_下发亲戚数据
- 接管定时器状态机：新手教学倒计时 / 进场倒计时 / 回合倒计时 / 结算停留
- 玩家图（玩家模板_UI第七关_游戏中_交互逻辑）仅保留 UI 点击入口，避免“广播信号在每个玩家图实例重复执行”的问题。

挂载实体：第七关关卡实体（GUID=1094713345）
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

关卡实体GUID: "GUID" = 1094713345

玩家变量_回合选择: "字符串" = "ui_battle_choice"  # 0/1/2（0=未选，1=allow，2=reject）
玩家变量_压岁钱: "字符串" = "ui_battle_money"
玩家变量_积分: "字符串" = "ui_battle_score"
玩家变量_排名: "字符串" = "ui_battle_rank"
玩家变量_压岁钱变化: "字符串" = "ui_battle_moneyd"
玩家变量_积分变化: "字符串" = "ui_battle_scored"
玩家变量_完整度: "字符串" = "ui_battle_integrity"
玩家变量_手办存活: "字符串" = "ui_battle_survival"
玩家变量_完整度变化: "字符串" = "ui_battle_integrityd"
玩家变量_手办存活变化: "字符串" = "ui_battle_survivald"

玩家变量_新手教程步骤: "字符串" = "ui_tut_step"  # 0=背景故事（guide_0），1~6=指引，7=完成页
玩家变量_新手教程完成: "字符串" = "ui_tut_done"  # 0/1

定时器名_进场倒计时: "字符串" = "ui_battle_entry_phase"
定时器名_回合倒计时: "字符串" = "ui_battle_stage_countdown"
定时器名_结算停留: "字符串" = "ui_battle_settlement_hold"
定时器名_新手教程倒计时: "字符串" = "ui_battle_tutorial_countdown"
定时器名_关门兜底: "字符串" = "ui_level7_door_close_fallback"

关卡变量_门关闭完成后待办: "字符串" = "第七关_门_关闭完成后待办"
关卡变量_本回合真相为允许: "字符串" = "第七关_本回合_真相为允许"
关卡变量_本回合是否小孩: "字符串" = "第七关_本回合_是否小孩"
关卡变量_本回合亲戚称谓: "字符串" = "第七关_本回合_亲戚称谓"

# 跨图共享状态：两个图（公共控制 + 玩家交互）通过关卡实体自定义变量读写同一份共享数据
关卡变量_当前阶段: "字符串" = "第七关_当前阶段"
关卡变量_已初始化: "字符串" = "第七关_已初始化"
关卡变量_已广播开局信号: "字符串" = "第七关_已广播开局信号"
关卡变量_当前回合序号: "字符串" = "第七关_当前回合序号"
关卡变量_本回合_对白列表: "字符串" = "第七关_本回合_对白列表"
关卡变量_本回合_对白序号: "字符串" = "第七关_本回合_对白序号"

# ---------------------------- 音频资源（BGM / 2D音效） ----------------------------
音量_满: "整数" = 100
播放速度_默认: "浮点数" = 1.0

# BGM
BGM_帮助阶段: "整数" = 10148
BGM_正式阶段: "整数" = 10123

# ---------------------------- 门流程（信号驱动；门动作由独立门控制图负责） ----------------------------
信号名_门动作: "字符串" = "第七关_门_动作"
信号名_结算派发: "字符串" = "第七关_结算派发"
信号名_回合推进派发: "字符串" = "第七关_回合推进派发"

# ---------------------------- 教程亲戚（帮助阶段展示，不进入回合状态机） ----------------------------
教程亲戚ID: "字符串" = "tutorial"
教程亲戚_称谓: "字符串" = "教程亲戚"
教程亲戚_真相为允许: "布尔值" = True
教程亲戚_外观_身体: "字符串" = "正常马"
教程亲戚_外观_头发: "字符串" = "普通头发"
教程亲戚_外观_胡子: "字符串" = "无"
教程亲戚_外观_眼镜: "字符串" = "无"
教程亲戚_外观_衣服: "字符串" = "西装"
教程亲戚_外观_领饰: "字符串" = "领带"
教程亲戚_对白1: "字符串" = "我是教程亲戚：先看看妈妈纸条，再做选择。"
教程亲戚_对白2: "字符串" = "等正式开始后，门会先关上，再换下一位亲戚。"
教程亲戚_对白3: "字符串" = "你可以随时点帮助回顾教程。"
教程亲戚_对白4: "字符串" = "准备好了就开始吧。"

# UI 控件/状态组占位符：写回阶段会解析为真实整数索引，不会以字符串落库。
允许按钮_enabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_allow_state__enabled__group"
允许按钮_disabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_allow_state__disabled__group"
拒绝按钮_enabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_reject_state__enabled__group"
拒绝按钮_disabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_reject_state__disabled__group"
帮助按钮_show组: "整数" = "ui_key:UI_STATE_GROUP__help_btn_state__show__group"
新手教程_guide_0组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__guide_0__group"
新手教程_guide_1组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__guide_1__group"
新手教程_guide_2组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__guide_2__group"
新手教程_guide_3组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__guide_3__group"
新手教程_guide_4组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__guide_4__group"
新手教程_guide_5组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__guide_5__group"
新手教程_guide_6组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__guide_6__group"
新手教程_done组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__done__group"
新手教程_wait_others组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_overlay__wait_others__group"
新手教程倒计时_show组: "整数" = "ui_key:UI_STATE_GROUP__tutorial_countdown_state__show__group"
游戏区倒计时_show组: "整数" = "ui_key:UI_STATE_GROUP__stage_countdown_state__show__group"
对白框_show组: "整数" = "ui_key:UI_STATE_GROUP__stage_dialogue_state__show__group"

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    # ---------------------------- 场景实体（动态查找） ----------------------------
    GraphVariableConfig(
        name="游戏场地GUID",
        variable_type="GUID",
        default_value="entity_key:第七关-场景",
        description="对外暴露：第七关场地实体 GUID。开局时用于传送玩家（Z-5）。使用 entity_key 占位符，写回阶段从参考 .gil 回填真实 GUID。",
        is_exposed=True,
    ),
    # ---------------------------- 结算统计（用于初始化玩家 HUD / 结算页展示） ----------------------------
    GraphVariableConfig(
        name="结算_完整度_初始值",
        variable_type="整数",
        default_value=100,
        description="对外暴露：第七关『年夜饭完整度』初始值（写回到玩家变量 ui_battle_integrity，UI 侧绑定 ps.ui_battle_integrity）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="结算_手办_初始值",
        variable_type="整数",
        default_value=10,
        description="对外暴露：第七关『手办存活数』初始值（写回到玩家变量 ui_battle_survival，UI 侧绑定 ps.ui_battle_survival）。",
        is_exposed=True,
    ),
    # ---------------------------- 审判庭字段 key 映射（避免在图逻辑中做字符串拼接/下标） ----------------------------
    GraphVariableConfig(
        name="审判_slot到名字Key",
        variable_type="整数-字符串字典",
        default_value={1: "审判1名", 2: "审判2名", 3: "审判3名", 4: "审判4名"},
        description="slot(1~4)→UI战斗_文本.<审判N名> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="审判_slot到分Key",
        variable_type="整数-字符串字典",
        default_value={1: "审判1分", 2: "审判2分", 3: "审判3分", 4: "审判4分"},
        description="slot(1~4)→UI战斗_文本.<审判N分> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="审判_slot到态Key",
        variable_type="整数-字符串字典",
        default_value={1: "审判1态", 2: "审判2态", 3: "审判3态", 4: "审判4态"},
        description="slot(1~4)→UI战斗_文本.<审判N态> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="手办存活数到文本",
        variable_type="整数-字符串字典",
        default_value={
            0: "0 / 10",
            1: "1 / 10",
            2: "2 / 10",
            3: "3 / 10",
            4: "4 / 10",
            5: "5 / 10",
            6: "6 / 10",
            7: "7 / 10",
            8: "8 / 10",
            9: "9 / 10",
            10: "10 / 10",
        },
        description="UI战斗_文本.存活 的展示文本（当前/最大）。最大值固定按 10 输出。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    # ---------------------------- 本回合数据（来自“亲戚数据服务”） ----------------------------
    # 重要：本回合真相/称谓/对白等会在多图间共享，因此统一写入「关卡实体自定义变量」，
    # 不使用节点图变量（节点图实例级隔离，跨图无法读取）。
    # （本回合_对白列表 / 本回合_对白序号 / 当前阶段 / 已初始化 / 已广播开局信号 / 当前回合序号
    #   已迁移为关卡实体自定义变量，见文件头部 关卡变量_xxx 常量定义）
    GraphVariableConfig(
        name="总回合数",
        variable_type="整数",
        default_value=10,
        description="总回合数：达到后切换到结算页。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="进场秒数",
        variable_type="整数",
        default_value=5,
        description="进场阶段秒数。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="回合倒计时秒数",
        variable_type="整数",
        default_value=20,
        description="投票阶段秒数。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="结算停留秒数",
        variable_type="整数",
        default_value=10,
        description="结果态停留秒数：用于自动推进下一回合；玩家点击『继续』会提前推进并终止本定时器。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="新手教程倒计时秒数",
        variable_type="整数",
        default_value=60,
        description="新手教程倒计时总秒数（UI战斗_整数.新手教程_剩余秒）。",
        is_exposed=False,
    ),
]


class 关卡实体_第七关_UI游戏中_公共控制:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_关卡大厅_开始关卡(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        第X关: "整数",
    ) -> None:
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        # 仅当确认进入“第七关”时才启动（避免被其它关卡的开始信号误触发）
        if 第X关 == 7:
            pass
        else:
            return

        # 信号触发开局：每次收到“开始第七关”都执行一次，作为强一致的 Reset+Init 入口（不依赖退出路径清状态）。
        # 先终止可能残留的定时器（上一局异常退出也能自愈；避免旧 tick 干扰新开局）
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_新手教程倒计时)
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进场倒计时)
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_回合倒计时)
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算停留)
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_关门兜底)

        # 强制重置阶段：确保无论上局停在哪个阶段，都能从“新手教学/帮助阶段（阶段=0）”重新开局
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段, 变量值=0, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已初始化, 变量值=True, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号, 变量值=False, 是否触发事件=False)

        当前阶段: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段)
        if 当前阶段 == 0:
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号, 变量值=1, 是否触发事件=False)
            在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
            初始完整度: "整数" = 获取节点图变量(self.game, 变量名="结算_完整度_初始值")
            初始手办: "整数" = 获取节点图变量(self.game, 变量名="结算_手办_初始值")
            for p in 在场玩家列表:
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_排名, 变量值=1, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱变化, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分变化, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度, 变量值=初始完整度, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度变化, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活, 变量值=初始手办, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活变化, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_新手教程步骤, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_新手教程完成, 变量值=0, 是否触发事件=False)

            # 传送玩家到第七关场景（场地实体位置 Z-5）
            场地GUID: "GUID" = 获取节点图变量(self.game, 变量名="游戏场地GUID")
            场地实体: "实体" = 以GUID查询实体(self.game, GUID=场地GUID)
            场地位置: "三维向量"
            场地旋转: "三维向量"
            场地位置, 场地旋转 = 获取实体位置与旋转(self.game, 目标实体=场地实体)
            传送偏移: "三维向量" = 创建三维向量(self.game, X分量=0.0, Y分量=0.0, Z分量=-5.0)
            传送目标位置: "三维向量" = 三维向量加法(self.game, 三维向量1=场地位置, 三维向量2=传送偏移)
            for p in 在场玩家列表:
                传送玩家(self.game, 玩家实体=p, 目标位置=传送目标位置, 目标旋转=场地旋转)

            # 清理可能残留的亲戚实体（避免重复进入时场上残留）
            旧实体_身体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_身体实体")
            销毁实体(self.game, 目标实体=旧实体_身体)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_身体实体", 变量值=0, 是否触发事件=False)
            旧实体_眼睛: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_眼睛实体")
            销毁实体(self.game, 目标实体=旧实体_眼睛)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_眼睛实体", 变量值=0, 是否触发事件=False)
            旧实体_头发: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_头发实体")
            销毁实体(self.game, 目标实体=旧实体_头发)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_头发实体", 变量值=0, 是否触发事件=False)
            旧实体_胡子: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_胡子实体")
            销毁实体(self.game, 目标实体=旧实体_胡子)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_胡子实体", 变量值=0, 是否触发事件=False)
            旧实体_领带: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_领带实体")
            销毁实体(self.game, 目标实体=旧实体_领带)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_领带实体", 变量值=0, 是否触发事件=False)
            旧实体_衣服: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_衣服实体")
            销毁实体(self.game, 目标实体=旧实体_衣服)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_衣服实体", 变量值=0, 是否触发事件=False)

            # 帮助阶段 BGM：进入第七关即切换
            for p in 在场玩家列表:
                修改玩家背景音乐(
                    self.game,
                    目标实体=p,
                    背景音乐索引=BGM_帮助阶段,
                    开始时间=0.0,
                    结束时间=9999.0,
                    音量=音量_满,
                    是否循环播放=True,
                    循环播放间隔=0.0,
                    播放速度=播放速度_默认,
                    是否允许渐入渐出=True,
                )

            # 门：帮助阶段先开一次门（门动作由《大门实体_第七关_门控制》统一处理）
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办, 变量值="无", 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合真相为允许, 变量值=True, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合是否小孩, 变量值=False, 是否触发事件=False)
            发送信号(self.game, 信号名=信号名_门动作, 目标状态="打开")

            # 教程阶段：刷新一次“教程亲戚”（仅用于帮助阶段展示；不驱动进场/投票状态机）
            教程对白列表: "字符串列表" = [教程亲戚_对白1, 教程亲戚_对白2, 教程亲戚_对白3, 教程亲戚_对白4]
            发送信号(
                self.game,
                信号名="第七关_下发亲戚数据",
                亲戚ID=教程亲戚ID,
                称谓=教程亲戚_称谓,
                真相为允许=教程亲戚_真相为允许,
                外观_身体=教程亲戚_外观_身体,
                外观_头发=教程亲戚_外观_头发,
                外观_胡子=教程亲戚_外观_胡子,
                外观_眼镜=教程亲戚_外观_眼镜,
                外观_衣服=教程亲戚_外观_衣服,
                外观_领饰=教程亲戚_外观_领饰,
                对白列表=教程对白列表,
            )

            # 教程亲戚打招呼：立即显示第一句对白（不等玩家点击"对话"按钮）
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合_对白列表, 变量值=教程对白列表, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合_对白序号, 变量值=1, 是否触发事件=False)
            battle_text_greeting: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")
            battle_text_greeting["对话"] = 教程亲戚_对白1
            for p in 在场玩家列表:
                修改界面布局内界面控件状态(self.game, p, 对白框_show组, "界面控件组状态_开启")

            # 结算页展示不再使用 UI结算_整数__* 镜像标量变量：进度条/数值标签统一绑定玩家变量
            # （ps.ui_battle_integrity / ps.ui_battle_survival），玩家侧已在“阶段=0”初始化完成。

            # # 初始化新手教程相关 UI 字典（保证 tutorial_overlay 文案有内容）
            # # 揭晓遮罩文案（UI战斗_揭晓）：本关卡仅使用 result 态（最终结果展示）
            # reveal_text: "字符串_字符串字典" = {
            #     "揭晓标题": "审判结果揭晓",
            #     "揭晓副标题": "本轮目标：—",
            #     "徽章_结果": "结果",
            #     "结果_判定": " ",
            #     "结果_真相": " ",
            #     "结果_描述": " ",
            #     "变化_完整度_标题": "年夜饭完整度",
            #     "变化_完整度": "0",
            #     "变化_存活_标题": "手办存活",
            #     "变化_存活": "0",
            #     "按钮_关闭": "继续",
            # }
            # 设置自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_揭晓", 变量值=reveal_text, 是否触发事件=False)

            # 审判庭初始展示：按在场玩家顺序填充前 4（思考中）
            player_count: "整数" = len(在场玩家列表)

            p1: "实体" = 在场玩家列表[0]
            pts1: "整数" = 获取自定义变量(self.game, 目标实体=p1, 变量名=玩家变量_积分)
            nick1: "字符串" = 获取玩家昵称(self.game, 玩家实体=p1)
            pts1_text: "字符串" = str(pts1)
            设置自定义变量(self.game, 目标实体=p1, 变量名=玩家变量_排名, 变量值=1, 是否触发事件=False)

            nick2: "字符串" = "—"
            pts2_text: "字符串" = "0"
            st2: "字符串" = " "
            if player_count >= 2:
                p2: "实体" = 在场玩家列表[1]
                pts2: "整数" = 获取自定义变量(self.game, 目标实体=p2, 变量名=玩家变量_积分)
                nick2 = 获取玩家昵称(self.game, 玩家实体=p2)
                pts2_text = str(pts2)
                st2_thinking: "字符串" = "思考中"
                st2 = st2_thinking
                设置自定义变量(self.game, 目标实体=p2, 变量名=玩家变量_排名, 变量值=2, 是否触发事件=False)

            nick3: "字符串" = "—"
            pts3_text: "字符串" = "0"
            st3: "字符串" = " "
            if player_count >= 3:
                p3: "实体" = 在场玩家列表[2]
                pts3: "整数" = 获取自定义变量(self.game, 目标实体=p3, 变量名=玩家变量_积分)
                nick3 = 获取玩家昵称(self.game, 玩家实体=p3)
                pts3_text = str(pts3)
                st3_thinking: "字符串" = "思考中"
                st3 = st3_thinking
                设置自定义变量(self.game, 目标实体=p3, 变量名=玩家变量_排名, 变量值=3, 是否触发事件=False)

            nick4: "字符串" = "—"
            pts4_text: "字符串" = "0"
            st4: "字符串" = " "
            if player_count >= 4:
                p4: "实体" = 在场玩家列表[3]
                pts4: "整数" = 获取自定义变量(self.game, 目标实体=p4, 变量名=玩家变量_积分)
                nick4 = 获取玩家昵称(self.game, 玩家实体=p4)
                pts4_text = str(pts4)
                st4_thinking: "字符串" = "思考中"
                st4 = st4_thinking
                设置自定义变量(self.game, 目标实体=p4, 变量名=玩家变量_排名, 变量值=4, 是否触发事件=False)

            # 初始化 UI战斗_文本：保留 HTML/UI 默认字典（如教程文案/纸条文案），仅覆盖“动态字段”（顶栏/审判庭）。
            # 关键：不要整包覆盖，否则会把默认字典里未包含的 key 清空，UI 会显示占位符。
            battle_text_init: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")

            # 倒计时 badge：进场阶段不展示倒计时（仅投票阶段显示）
            battle_text_init["回合倒计时"] = " "

            # 审判庭标题 + 按在场玩家顺序填充前 4（思考中）
            battle_text_init["审判标题"] = "亲戚审判庭"
            battle_text_init["审判1名"] = nick1
            battle_text_init["审判1分"] = pts1_text
            battle_text_init["审判1态"] = "思考中"
            battle_text_init["审判2名"] = nick2
            battle_text_init["审判2分"] = pts2_text
            battle_text_init["审判2态"] = st2
            battle_text_init["审判3名"] = nick3
            battle_text_init["审判3分"] = pts3_text
            battle_text_init["审判3态"] = st3
            battle_text_init["审判4名"] = nick4
            battle_text_init["审判4分"] = pts4_text
            battle_text_init["审判4态"] = st4

            # 审判庭状态颜色：与 UI战斗_文本.审判N态 同步（避免多人 slot2/3/4 仍使用默认绿/红）
            style_colors: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI样式_颜色")
            c_thinking: "字符串" = style_colors["状态_思考中"]
            battle_color_init: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_颜色")
            battle_color_init["审判1态"] = c_thinking
            battle_color_init["审判2态"] = c_thinking
            battle_color_init["审判3态"] = c_thinking
            battle_color_init["审判4态"] = c_thinking

            # 初始化 UI战斗_整数（倒计时/人数）
            教程总秒: "整数" = 获取节点图变量(self.game, 变量名="新手教程倒计时秒数")
            battle_int: "字符串_整数字典" = {
                "新手教程_剩余秒": 教程总秒,
                "新手教程_已完成人数": 0,
                "新手教程_总人数": len(在场玩家列表),
            }
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_整数", 变量值=battle_int, 是否触发事件=False)

            # 顶栏右上角：剩余亲戚（UI房间_文本：由 HTML 拼接 current / total，避免节点图侧做字符串拼接）
            room_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI房间_文本")
            当前回合: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号)
            总回合: "整数" = 获取节点图变量(self.game, 变量名="总回合数")
            diff: "整数" = (总回合 - 当前回合)
            剩余_raw: "整数" = (diff + 1)
            剩余: "整数" = max(0, 剩余_raw)
            剩余文本: "字符串" = str(剩余)
            总回合文本: "字符串" = str(总回合)
            room_text["剩余亲戚_当前"] = 剩余文本
            room_text["剩余亲戚_总"] = 总回合文本

            # 启动新手教程倒计时（循环定时器：每秒 tick；用 循环次数 驱动递减，避免维护超长序列）
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_新手教程倒计时)
            启动定时器(
                self.game,
                目标实体=关卡实体,
                定时器名称=定时器名_新手教程倒计时,
                是否循环=True,
                定时器序列=[1.0],
            )

            # 打开新手教程遮罩，并隐藏帮助按钮/显示倒计时（正式开始后再显示帮助并隐藏倒计时）
            for p in 在场玩家列表:
                修改界面布局内界面控件状态(self.game, p, 帮助按钮_show组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程倒计时_show组, "界面控件组状态_开启")

                修改界面布局内界面控件状态(self.game, p, 新手教程_guide_1组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_guide_2组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_guide_3组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_guide_4组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_guide_5组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_guide_6组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_done组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_wait_others组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, 新手教程_guide_0组, "界面控件组状态_开启")

            # 阶段仍保持 0：等待『第七关_开始游戏』信号后再进入进场阶段（启动进场倒计时/解锁帮助/隐藏倒计时）
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段, 变量值=0, 是否触发事件=False)
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进场倒计时)
            # 进场倒计时在『第七关_开始游戏』信号后启动
        return

    def on_第七关_开始游戏(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
    ) -> None:
        """第七关开局信号：新手教学倒计时结束或全员完成后触发。

        口径：
        - 隐藏新手教学倒计时；
        - 关闭新手教学遮罩（guide/wait/done）；
        - 显示帮助按钮（用于个人回顾教程）；
        - 进入“进场阶段”，启动进场倒计时。
        """
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        已初始化: "布尔值" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已初始化)
        if 已初始化:
            pass
        else:
            return

        当前阶段: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段)
        if 当前阶段 == 0:
            pass
        else:
            return

        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号, 变量值=True, 是否触发事件=False)

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)

        # 正式阶段 BGM：新手教学结束 → 切换
        for p in 在场玩家列表:
            修改玩家背景音乐(
                self.game,
                目标实体=p,
                背景音乐索引=BGM_正式阶段,
                开始时间=0.0,
                结束时间=9999.0,
                音量=音量_满,
                是否循环播放=True,
                循环播放间隔=0.0,
                播放速度=播放速度_默认,
                是否允许渐入渐出=True,
            )

        # 停止新手教程倒计时（若仍在 tick）
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_新手教程倒计时)

        # 正式开局：将所有“战斗/结算”关键数据重置为初始状态（教程阶段不污染正式对局）
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号, 变量值=1, 是否触发事件=False)

        # 顶栏右上角：剩余亲戚（UI房间_文本）
        room_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI房间_文本")
        当前回合: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号)
        总回合: "整数" = 获取节点图变量(self.game, 变量名="总回合数")
        diff: "整数" = (总回合 - 当前回合)
        剩余_raw: "整数" = (diff + 1)
        剩余: "整数" = max(0, 剩余_raw)
        剩余文本: "字符串" = str(剩余)
        总回合文本: "字符串" = str(总回合)
        room_text["剩余亲戚_当前"] = 剩余文本
        room_text["剩余亲戚_总"] = 总回合文本

        初始完整度: "整数" = 获取节点图变量(self.game, 变量名="结算_完整度_初始值")
        初始手办: "整数" = 获取节点图变量(self.game, 变量名="结算_手办_初始值")
        for p in 在场玩家列表:
            # 正式开局：重置玩家对局数据（压岁钱/投票选择等）
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_排名, 变量值=1, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱变化, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分变化, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度, 变量值=初始完整度, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度变化, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活, 变量值=初始手办, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活变化, 变量值=0, 是否触发事件=False)

            # 解锁帮助（个人回顾）
            修改界面布局内界面控件状态(self.game, p, 帮助按钮_show组, "界面控件组状态_开启")

            # 隐藏开局倒计时
            修改界面布局内界面控件状态(self.game, p, 新手教程倒计时_show组, "界面控件组状态_关闭")

            # 关闭新手教学遮罩（无论玩家当前在 guide/done/wait 哪一页）
            修改界面布局内界面控件状态(self.game, p, 新手教程_guide_0组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_guide_1组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_guide_2组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_guide_3组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_guide_4组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_guide_5组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_guide_6组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_done组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, p, 新手教程_wait_others组, "界面控件组状态_关闭")

        # 正式开局：初始化 UI战斗_文本（保留默认字典，仅覆盖必要的动态字段）
        battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")

        # 倒计时 badge：进场阶段不展示倒计时（仅投票阶段显示）
        battle_text["回合倒计时"] = " "

        slot_to_name_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到名字Key")
        slot_to_pts_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到分Key")
        slot_to_state_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到态Key")
        style_colors: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI样式_颜色")
        c_thinking: "字符串" = style_colors["状态_思考中"]
        battle_color: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_颜色")
        player_count: "整数" = len(在场玩家列表)
        slots: "整数列表" = [1, 2, 3, 4]
        for slot in slots:
            name_key: "字符串" = slot_to_name_key[slot]
            pts_key: "字符串" = slot_to_pts_key[slot]
            state_key: "字符串" = slot_to_state_key[slot]
            if player_count >= slot:
                idx: "整数" = (slot - 1)
                p: "实体" = 在场玩家列表[idx]
                nick: "字符串" = 获取玩家昵称(self.game, 玩家实体=p)
                pts: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
                pts_text: "字符串" = str(pts)
                battle_text[name_key] = nick
                battle_text[pts_key] = pts_text
                battle_text[state_key] = "思考中"
                battle_color[state_key] = c_thinking
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_排名, 变量值=slot, 是否触发事件=False)
            else:
                battle_text[name_key] = "—"
                battle_text[pts_key] = "0"
                if slot == 4:
                    battle_text[state_key] = " "
                else:
                    battle_text[state_key] = " "
                battle_color[state_key] = c_thinking

        # 帮助结束：先关门；关门完成后生成第 1 回合亲戚并开门进场
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办, 变量值="开局", 是否触发事件=False)
        for p in 在场玩家列表:
            修改界面布局内界面控件状态(self.game, p, 对白框_show组, "界面控件组状态_关闭")
        发送信号(self.game, 信号名=信号名_门动作, 目标状态="关闭")
        return

    def on_第七关_下发本局纸条(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        线索标题: "字符串",
        线索标签列表: "字符串列表",
        线索文本列表: "字符串列表",
    ) -> None:
        """数据服务下发：本局妈妈纸条（线索面板）。"""
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")

        battle_text["线索标题"] = 线索标题

        t1: "字符串" = 线索标签列表[0]
        t2: "字符串" = 线索标签列表[1]
        t3: "字符串" = 线索标签列表[2]
        t4: "字符串" = 线索标签列表[3]
        t5: "字符串" = 线索标签列表[4]
        t6: "字符串" = 线索标签列表[5]
        battle_text["线索1标"] = t1
        battle_text["线索2标"] = t2
        battle_text["线索3标"] = t3
        battle_text["线索4标"] = t4
        battle_text["线索5标"] = t5
        battle_text["线索6标"] = t6

        x1: "字符串" = 线索文本列表[0]
        x2: "字符串" = 线索文本列表[1]
        x3: "字符串" = 线索文本列表[2]
        x4: "字符串" = 线索文本列表[3]
        x5: "字符串" = 线索文本列表[4]
        x6: "字符串" = 线索文本列表[5]

        battle_text["线索1文"] = x1
        battle_text["线索2文"] = x2
        battle_text["线索3文"] = x3
        battle_text["线索4文"] = x4
        battle_text["线索5文"] = x5
        battle_text["线索6文"] = x6
        return

    def on_第七关_下发亲戚数据(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        亲戚ID: "字符串",
        称谓: "字符串",
        真相为允许: "布尔值",
        外观_身体: "字符串",
        外观_头发: "字符串",
        外观_胡子: "字符串",
        外观_眼镜: "字符串",
        外观_衣服: "字符串",
        外观_领饰: "字符串",
        对白列表: "字符串列表",
    ) -> None:
        """数据服务下发：本回合来访者数据。负责按外观查表生成元件，并进入进场阶段。"""
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        # 教程阶段也会刷新一次“教程亲戚”用于展示（亲戚ID=tutorial）；
        # 公共控制图在正式开始前不进入进场/投票状态机。
        已正式开始: "布尔值" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号)
        if 已正式开始:
            pass
        else:
            return

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)

        # 进场阶段：隐藏游戏区倒计时 badge（本阶段仍会等待，但不对玩家展示倒计时）
        for p in 在场玩家列表:
            修改界面布局内界面控件状态(self.game, p, 游戏区倒计时_show组, "界面控件组状态_关闭")

        # 缓存本回合真相/称谓/对白（投票揭晓与对话按钮使用）
        是否小孩: "布尔值" = 外观_身体 == "小孩马"
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合真相为允许, 变量值=真相为允许, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合是否小孩, 变量值=是否小孩, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合亲戚称谓, 变量值=称谓, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合_对白列表, 变量值=对白列表, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合_对白序号, 变量值=0, 是否触发事件=False)

        # 避免上一回合对白残留：清空显示（UI 侧“空文本”请用单空格占位）
        battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")
        battle_text["对话"] = " "
        battle_text["回合倒计时"] = " "

        # 新亲戚出现后：对白框默认隐藏（只有首次点击“对话”才显示黑框）
        for p in 在场玩家列表:
            修改界面布局内界面控件状态(self.game, p, 对白框_show组, "界面控件组状态_关闭")

        # 亲戚生成与开门动作由「关卡实体挂载图」执行：关卡实体_第七关_门后流程与亲戚生成

        # 进入进场阶段（进场倒计时结束后进入投票阶段）
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段, 变量值=1, 是否触发事件=False)
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进场倒计时)
        启动定时器(
            self.game,
            目标实体=关卡实体,
            定时器名称=定时器名_进场倒计时,
            是否循环=True,
            定时器序列=[1.0],
        )
        return

    def on_第七关_结算派发(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        允许票: "整数",
        拒绝票: "整数",
    ) -> None:
        """结算派发后：启动“结果态停留”定时器，到点由本图派发回合推进。"""
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        当前阶段: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段)
        if 当前阶段 == 3:
            pass
        else:
            return

        # 结算停留：用循环定时器按秒 tick，避免跨图/跨语义依赖“定时器序列序号”的口径。
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算停留)
        启动定时器(
            self.game,
            目标实体=关卡实体,
            定时器名称=定时器名_结算停留,
            是否循环=True,
            定时器序列=[1.0],
        )
        return

    def on_定时器触发时(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        定时器名称: "字符串",
        定时器序列序号: "整数",
        循环次数: "整数",
    ):
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)

        # 新手教程倒计时：每秒递减 UI战斗_整数.新手教程_剩余秒
        if 定时器名称 == 定时器名_新手教程倒计时:
            当前阶段: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段)
            if 当前阶段 == 0:
                pass
            else:
                # 已正式开始：不再需要开局倒计时
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_新手教程倒计时)
                return

            总秒: "整数" = 获取节点图变量(self.game, 变量名="新手教程倒计时秒数")
            # 循环定时器：每秒触发一次；循环次数从 0 开始计数，因此用 +1 得到已过去秒数
            已过去: "整数" = 加法运算(self.game, 左值=循环次数, 右值=1)
            剩余_raw: "整数" = 减法运算(self.game, 左值=总秒, 右值=已过去)
            剩余: "整数" = max(0, 剩余_raw)
            battle_int: "字符串_整数字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_整数")
            对字典设置或新增键值对(self.game, 字典=battle_int, 键="新手教程_剩余秒", 值=剩余)

            if 剩余 == 0:
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_新手教程倒计时)
                已广播开局信号: "布尔值" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号)
                if 已广播开局信号:
                    return
                else:
                    pass

                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号, 变量值=True, 是否触发事件=False)
                发送信号(self.game, 信号名="第七关_开始游戏")
            return

        # 进场倒计时：结束后进入投票阶段并启动回合倒计时
        if 定时器名称 == 定时器名_进场倒计时:
            进场总秒: "整数" = 获取节点图变量(self.game, 变量名="进场秒数")
            已过去: "整数" = 加法运算(self.game, 左值=循环次数, 右值=1)
            剩余: "整数" = 减法运算(self.game, 左值=进场总秒, 右值=已过去)
            if 剩余 == 0:
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进场倒计时)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段, 变量值=2, 是否触发事件=False)

                # 进入投票阶段：按钮恢复可用 + 审判1态重置为思考中
                for p in 在场玩家列表:
                    修改界面布局内界面控件状态(self.game, p, 允许按钮_disabled组, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, 允许按钮_enabled组, "界面控件组状态_开启")
                    修改界面布局内界面控件状态(self.game, p, 拒绝按钮_disabled组, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, 拒绝按钮_enabled组, "界面控件组状态_开启")
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择, 变量值=0, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱变化, 变量值=0, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分变化, 变量值=0, 是否触发事件=False)
                battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")

                # 刷新审判庭：按积分排名展示（进入投票阶段：所有状态回到思考中；同分按在场顺序稳定）
                slot_to_name_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到名字Key")
                slot_to_pts_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到分Key")
                slot_to_state_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到态Key")

                style_colors: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI样式_颜色")
                c_thinking: "字符串" = 以键查询字典值(self.game, 字典=style_colors, 键="状态_思考中")
                battle_color: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_颜色")

                player_count: "整数" = 获取列表长度(self.game, 列表=在场玩家列表)
                p0: "实体" = 获取列表对应值(self.game, 列表=在场玩家列表, 序号=0)
                p0_pts: "整数" = 获取自定义变量(self.game, 目标实体=p0, 变量名=玩家变量_积分)
                score_dict: "实体-整数字典" = {p0: p0_pts}
                for p in 在场玩家列表:
                    pts: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
                    对字典设置或新增键值对(self.game, 字典=score_dict, 键=p, 值=pts)

                sorted_players, sorted_scores = 对字典按值排序(self.game, 字典=score_dict, 排序方式="排序规则_逆序")

                slots: "整数列表" = [1, 2, 3, 4]
                for slot in slots:
                    name_key: "字符串" = 以键查询字典值(self.game, 字典=slot_to_name_key, 键=slot)
                    pts_key: "字符串" = 以键查询字典值(self.game, 字典=slot_to_pts_key, 键=slot)
                    state_key: "字符串" = 以键查询字典值(self.game, 字典=slot_to_state_key, 键=slot)
                    if player_count >= slot:
                        idx: "整数" = 减法运算(self.game, 左值=slot, 右值=1)
                        p: "实体" = 获取列表对应值(self.game, 列表=sorted_players, 序号=idx)
                        pts: "整数" = 获取列表对应值(self.game, 列表=sorted_scores, 序号=idx)
                        pts_text: "字符串" = str(pts)
                        nick: "字符串" = 获取玩家昵称(self.game, 玩家实体=p)
                        对字典设置或新增键值对(self.game, 字典=battle_text, 键=name_key, 值=nick)
                        对字典设置或新增键值对(self.game, 字典=battle_text, 键=pts_key, 值=pts_text)
                        对字典设置或新增键值对(self.game, 字典=battle_text, 键=state_key, 值="思考中")
                        对字典设置或新增键值对(self.game, 字典=battle_color, 键=state_key, 值=c_thinking)
                        设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_排名, 变量值=slot, 是否触发事件=False)
                    else:
                        对字典设置或新增键值对(self.game, 字典=battle_text, 键=name_key, 值="—")
                        对字典设置或新增键值对(self.game, 字典=battle_text, 键=pts_key, 值="0")
                        对字典设置或新增键值对(self.game, 字典=battle_text, 键=state_key, 值=" ")
                        对字典设置或新增键值对(self.game, 字典=battle_color, 键=state_key, 值=c_thinking)

                # 投票阶段倒计时：先写回初始值（如 20），避免显示上个阶段残留数值
                回合总秒: "整数" = 获取节点图变量(self.game, 变量名="回合倒计时秒数")
                对字典设置或新增键值对(self.game, 字典=battle_text, 键="回合倒计时", 值=str(回合总秒))

                # 投票阶段：显示游戏区倒计时 badge（确保显示时已写入初始值）
                for p in 在场玩家列表:
                    修改界面布局内界面控件状态(self.game, p, 游戏区倒计时_show组, "界面控件组状态_开启")
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_回合倒计时)
                启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_回合倒计时, 是否循环=True, 定时器序列=[1.0])
            return

        # 回合倒计时：到 0 自动结算并揭晓（未操作默认允许）
        if 定时器名称 == 定时器名_回合倒计时:
            总秒: "整数" = 获取节点图变量(self.game, 变量名="回合倒计时秒数")
            已过去: "整数" = 加法运算(self.game, 左值=循环次数, 右值=1)
            剩余: "整数" = 减法运算(self.game, 左值=总秒, 右值=已过去)
            battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")
            剩余文本: "字符串" = str(剩余)
            对字典设置或新增键值对(self.game, 字典=battle_text, 键="回合倒计时", 值=剩余文本)
            if 剩余 == 0:
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_回合倒计时)
                当前阶段: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段)
                if 当前阶段 == 2:
                    # 超时：把未选择的玩家默认写为“允许(1)”，然后立即揭晓
                    for p in 在场玩家列表:
                        c: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择)
                        if c == 0:
                            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择, 变量值=1, 是否触发事件=False)

                    # 停止投票倒计时，进入结算阶段
                    终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_回合倒计时)
                    设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段, 变量值=3, 是否触发事件=False)

                    # 结算阶段：锁定操作按钮（无论此前是否已被禁用）
                    for p in 在场玩家列表:
                        修改界面布局内界面控件状态(self.game, p, 允许按钮_enabled组, "界面控件组状态_关闭")
                        修改界面布局内界面控件状态(self.game, p, 允许按钮_disabled组, "界面控件组状态_开启")
                        修改界面布局内界面控件状态(self.game, p, 拒绝按钮_enabled组, "界面控件组状态_关闭")
                        修改界面布局内界面控件状态(self.game, p, 拒绝按钮_disabled组, "界面控件组状态_开启")

                    # 结算阶段：隐藏游戏区倒计时 badge（避免结果遮罩关闭后的短暂过渡露出倒计时）
                    for p in 在场玩家列表:
                        修改界面布局内界面控件状态(self.game, p, 游戏区倒计时_show组, "界面控件组状态_关闭")
                    battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")
                    对字典设置或新增键值对(self.game, 字典=battle_text, 键="回合倒计时", 值=" ")

                    # 统计票数（超时默认允许后：不会再出现 c==0）
                    允许票: "整数" = 0
                    拒绝票: "整数" = 0
                    for p in 在场玩家列表:
                        c: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择)
                        if c == 1:
                            允许票 = 加法运算(self.game, 左值=允许票, 右值=1)
                        else:
                            拒绝票 = 加法运算(self.game, 左值=拒绝票, 右值=1)

                    # 公共结算由关卡实体执行：通过信号参数传递票数。
                    发送信号(self.game, 信号名=信号名_结算派发, 允许票=允许票, 拒绝票=拒绝票)
                    return
            return

        # 结算停留：到 0 自动推进下一回合并重新进场；到达总回合数则切结算页
        if 定时器名称 == 定时器名_结算停留:
            总秒: "整数" = 获取节点图变量(self.game, 变量名="结算停留秒数")
            已过去: "整数" = 加法运算(self.game, 左值=循环次数, 右值=1)
            剩余_raw: "整数" = 减法运算(self.game, 左值=总秒, 右值=已过去)
            剩余: "整数" = max(0, 剩余_raw)
            if 剩余 == 0:
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算停留)
                # 统一由回合推进执行图负责“回合序号递增/剩余亲戚刷新/关门待办写入/关门动作”。
                当前回合: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号)
                总回合: "整数" = 获取节点图变量(self.game, 变量名="总回合数")
                下一回合: "整数" = 加法运算(self.game, 左值=当前回合, 右值=1)
                if 下一回合 > 总回合:
                    最后一回合标记: "整数" = 1
                else:
                    最后一回合标记: "整数" = 0
                发送信号(self.game, 信号名=信号名_回合推进派发, 是否最后回合=最后一回合标记)
            return

        return

    def register_handlers(self):
        self.game.register_event_handler(
            "定时器触发时",
            self.on_定时器触发时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "关卡大厅_开始关卡",
            self.on_关卡大厅_开始关卡,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_开始游戏",
            self.on_第七关_开始游戏,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_下发本局纸条",
            self.on_第七关_下发本局纸条,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_下发亲戚数据",
            self.on_第七关_下发亲戚数据,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_结算派发",
            self.on_第七关_结算派发,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

