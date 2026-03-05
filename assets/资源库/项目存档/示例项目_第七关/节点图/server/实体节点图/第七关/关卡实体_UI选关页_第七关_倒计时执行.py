"""
graph_id: server_test_project_ui_level_select_level7_timer_executor
graph_name: 关卡实体_UI选关页_第七关_倒计时执行
graph_type: server
description: 选关/预览/倒计时/回合推进综合执行图（关卡实体单实例）：

- 接管关卡实体定时器回调：进入关卡倒计时 / 投票取消提示 / 结算提示 / 通关 UI 同步
- 接管选关预览：刷新预览 / 清空全员预览（预览配置由玩家图写入关卡实体自定义变量，本图读取并执行）
- 接管大厅交互：关卡大厅_前往选关（传送/职业切换/隐藏模型），并在 0.5 秒后同步通关印章
- 接管第七关公共回合推进：监听信号 `第七关_回合推进派发(是否最后回合)`，执行“结算后推进”公共逻辑并发送关门动作
- 玩家图（玩家模板_UI选关页_第七关_交互逻辑）仅保留 UI 点击入口，避免多人环境下倒计时末端逻辑重复执行。

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

# 选关职业：用于展示选关面板
选关职业配置ID: "配置ID" = 1090519049

玩家变量_投票关卡: "字符串" = "ui_vote_level"
玩家变量_投票结算: "字符串" = "ui_vote_settle"
玩家变量_玩家序号: "字符串" = "ui_player_index"

# 选关预览：存放“预览元件实体引用（实体）”。
# 说明：通过【创建元件】生成的运行时实体在真机侧通常没有可用 GUID，因此预览清理不要依赖 GUID。
玩家变量_预览关卡: "字符串" = "ui_preview_level"
玩家变量_预览实体1: "字符串" = "ui_preview_entity_1"
玩家变量_预览实体2: "字符串" = "ui_preview_entity_2"

# 第七关回合推进（公共执行）
玩家变量_回合选择: "字符串" = "ui_battle_choice"
信号名_门动作: "字符串" = "第七关_门_动作"
关卡变量_门关闭完成后待办: "字符串" = "第七关_门_关闭完成后待办"
关卡变量_当前阶段: "字符串" = "第七关_当前阶段"
关卡变量_当前回合序号: "字符串" = "第七关_当前回合序号"

定时器名_进入倒计时: "字符串" = "ui_level_select_enter_countdown"
定时器名_投票取消提示: "字符串" = "ui_level_select_vote_cancel_tip"
定时器名_结算提示: "字符串" = "ui_level_select_settle_tip"
定时器名_通关UI同步: "字符串" = "level_lobby_sync_cleared_ui"

信号名_刷新预览: "字符串" = "UI选关页_第七关_刷新预览"
信号名_清空全员预览: "字符串" = "UI选关页_第七关_清空全员预览"

# 跨图共享状态：投票倒计时锁通过关卡实体自定义变量协调（玩家图写入、本图回调读取）
选关_投票倒计时_进行中: "字符串" = "选关_投票倒计时_进行中"
选关_投票倒计时_模式: "字符串" = "选关_投票倒计时_模式"
选关_投票倒计时_目标关卡: "字符串" = "选关_投票倒计时_目标关卡"

# UI 控件/状态组占位符：写回阶段会解析为真实整数索引，不会以字符串落库。
投票取消提示_show组: "整数" = "ui_key:UI_STATE_GROUP__vote_cancel_tip__show__group"
结算提示_show组: "整数" = "ui_key:UI_STATE_GROUP__settle_tip__show__group"
# 投票遮罩与投票按钮状态组（选关页 UI）
投票遮罩_show组: "整数" = "ui_key:UI_STATE_GROUP__vote_overlay__show__group"
投票按钮_enabled组: "整数" = "ui_key:UI_STATE_GROUP__rect_btn_start__enabled__group"
投票按钮_disabled组: "整数" = "ui_key:UI_STATE_GROUP__rect_btn_start__disabled__group"
# 回合推进用：结算遮罩/对白框（关闭）
揭晓遮罩_result组: "整数" = "ui_key:UI_STATE_GROUP__battle_settlement_overlay__result__group"
对白框_show组: "整数" = "ui_key:UI_STATE_GROUP__stage_dialogue_state__show__group"

# 通关印章 show 组（选关页 UI）
关卡号到通关标记_show组: "整数-整数字典" = {
    1: "ui_key:UI_STATE_GROUP__level_cleared_mark_01__show__group",
    2: "ui_key:UI_STATE_GROUP__level_cleared_mark_02__show__group",
    3: "ui_key:UI_STATE_GROUP__level_cleared_mark_03__show__group",
    4: "ui_key:UI_STATE_GROUP__level_cleared_mark_04__show__group",
    5: "ui_key:UI_STATE_GROUP__level_cleared_mark_05__show__group",
    6: "ui_key:UI_STATE_GROUP__level_cleared_mark_06__show__group",
    7: "ui_key:UI_STATE_GROUP__level_cleared_mark_07__show__group",
    8: "ui_key:UI_STATE_GROUP__level_cleared_mark_08__show__group",
    9: "ui_key:UI_STATE_GROUP__level_cleared_mark_09__show__group",
    10: "ui_key:UI_STATE_GROUP__level_cleared_mark_10__show__group",
}

# 关卡按钮状态组（选关页 UI）
关卡号到未选组映射: "整数-整数字典" = {
    1: "ui_key:UI_STATE_GROUP__rect_level_01__unselected__group",
    2: "ui_key:UI_STATE_GROUP__rect_level_02__unselected__group",
    3: "ui_key:UI_STATE_GROUP__rect_level_03__unselected__group",
    4: "ui_key:UI_STATE_GROUP__rect_level_04__unselected__group",
    5: "ui_key:UI_STATE_GROUP__rect_level_05__unselected__group",
    6: "ui_key:UI_STATE_GROUP__rect_level_06__unselected__group",
    7: "ui_key:UI_STATE_GROUP__rect_level_07__unselected__group",
    8: "ui_key:UI_STATE_GROUP__rect_level_08__unselected__group",
    9: "ui_key:UI_STATE_GROUP__rect_level_09__unselected__group",
    10: "ui_key:UI_STATE_GROUP__rect_level_10__unselected__group",
}
关卡号到已选组映射: "整数-整数字典" = {
    1: "ui_key:UI_STATE_GROUP__rect_level_01__selected__group",
    2: "ui_key:UI_STATE_GROUP__rect_level_02__selected__group",
    3: "ui_key:UI_STATE_GROUP__rect_level_03__selected__group",
    4: "ui_key:UI_STATE_GROUP__rect_level_04__selected__group",
    5: "ui_key:UI_STATE_GROUP__rect_level_05__selected__group",
    6: "ui_key:UI_STATE_GROUP__rect_level_06__selected__group",
    7: "ui_key:UI_STATE_GROUP__rect_level_07__selected__group",
    8: "ui_key:UI_STATE_GROUP__rect_level_08__selected__group",
    9: "ui_key:UI_STATE_GROUP__rect_level_09__selected__group",
    10: "ui_key:UI_STATE_GROUP__rect_level_10__selected__group",
}
关卡号到禁用组映射: "整数-整数字典" = {
    1: "ui_key:UI_STATE_GROUP__rect_level_01__disabled__group",
    2: "ui_key:UI_STATE_GROUP__rect_level_02__disabled__group",
    3: "ui_key:UI_STATE_GROUP__rect_level_03__disabled__group",
    4: "ui_key:UI_STATE_GROUP__rect_level_04__disabled__group",
    5: "ui_key:UI_STATE_GROUP__rect_level_05__disabled__group",
    6: "ui_key:UI_STATE_GROUP__rect_level_06__disabled__group",
    7: "ui_key:UI_STATE_GROUP__rect_level_07__disabled__group",
    8: "ui_key:UI_STATE_GROUP__rect_level_08__disabled__group",
    9: "ui_key:UI_STATE_GROUP__rect_level_09__disabled__group",
    10: "ui_key:UI_STATE_GROUP__rect_level_10__disabled__group",
}

# 关卡实体自定义变量名：由玩家图在交互前写入，本图只读取并执行。
关卡实体自定义变量名_预览配置_关卡号到展示元件ID_1: "字符串" = "UI选关_预览_展示元件ID_1"
关卡实体自定义变量名_预览配置_关卡号到展示元件ID_2: "字符串" = "UI选关_预览_展示元件ID_2"
关卡实体自定义变量名_预览配置_关卡号到展示位置偏移: "字符串" = "UI选关_预览配置_关卡号到展示位置偏移"
关卡实体自定义变量名_预览配置_关卡号到第二元件自带偏移: "字符串" = "UI选关_预览_第二元件偏移"
关卡实体自定义变量名_预览配置_关卡号到展示旋转_1: "字符串" = "UI选关_预览配置_关卡号到展示旋转_1"
关卡实体自定义变量名_预览配置_关卡号到展示旋转_2: "字符串" = "UI选关_预览配置_关卡号到展示旋转_2"

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="布局索引_第七关游戏中",
        variable_type="整数",
        default_value=0,
        description="UI布局索引：第七关游戏中页（第七关-游戏中.html）。默认 0；写回阶段会尝试用 ui_guid_registry 的 LAYOUT_INDEX__HTML__第七关-游戏中 自动回填。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="进入倒计时秒数",
        variable_type="整数",
        default_value=3,
        description="投票达成后进入已投票关卡的倒计时秒数（UI选关_投票.countdown_sec）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="总回合数",
        variable_type="整数",
        default_value=10,
        description="总回合数：达到后切换到结算页（用于回合推进执行中的『是否最后回合』判定与右上角剩余亲戚刷新）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="玩家序号到玩家位置GUID",
        variable_type="整数-GUID字典",
        default_value={
            1: 1077952505,
            2: 1077952506,
            3: 1077952507,
            4: 1077952508,
        },
        description="玩家序号（1~4）→玩家站位实体 GUID（玩家进入/重置选关时会被传送到各自站位）。GUID 需由作者回填。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="GUID",
    ),
    GraphVariableConfig(
        name="关卡号到通关Key",
        variable_type="整数-字符串字典",
        default_value={
            1: "level_01_cleared",
            2: "level_02_cleared",
            3: "level_03_cleared",
            4: "level_04_cleared",
            5: "level_05_cleared",
            6: "level_06_cleared",
            7: "level_07_cleared",
            8: "level_08_cleared",
            9: "level_09_cleared",
            10: "level_10_cleared",
        },
        description="关卡号→通关记录字段 key（位于 `UI选关_列表` 字典，例如 level_07_cleared）。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
]


class 关卡实体_UI选关页_第七关_倒计时执行:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_关卡大厅_前往选关(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
    ) -> None:
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        # 进入选关：清理投票倒计时锁与提示定时器，避免跨页面残留
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时)
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_投票取消提示)
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_进行中, 变量值=0, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式, 变量值="无", 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_目标关卡, 变量值=0, 是否触发事件=False)

        # 门流程待办锁：清为“无”
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办, 变量值="无", 是否触发事件=False)

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
        玩家位置GUID表: "整数-GUID字典" = 获取节点图变量(self.game, 变量名="玩家序号到玩家位置GUID")

        for p in 在场玩家列表:
            玩家GUID: "GUID" = 以实体查询GUID(self.game, 实体=p)
            玩家序号: "整数" = 根据玩家GUID获取玩家序号(self.game, 玩家GUID=玩家GUID)
            玩家位置GUID: "GUID" = 玩家位置GUID表[玩家序号]
            玩家位置实体: "实体" = 以GUID查询实体(self.game, GUID=玩家位置GUID)
            位置: "三维向量"
            旋转: "三维向量"
            位置, 旋转 = 获取实体位置与旋转(self.game, 目标实体=玩家位置实体)

            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_玩家序号, 变量值=玩家序号, 是否触发事件=False)

            传送玩家(self.game, 玩家实体=p, 目标位置=位置, 目标旋转=旋转)
            启动暂停玩家背景音乐(self.game, 目标实体=p, 是否恢复=False)
            更改玩家职业(self.game, 目标玩家=p, 职业配置ID=选关职业配置ID)
            激活关闭模型显示(self.game, 目标实体=p, 是否激活=False)

        # 延迟 0.5 秒同步通关 UI：等待选关面板完成初始化（职业切换/传送后首帧可能尚未就绪）
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_通关UI同步)
        启动定时器(
            self.game,
            目标实体=关卡实体,
            定时器名称=定时器名_通关UI同步,
            是否循环=False,
            定时器序列=[0.5],
        )
        return

    def on_UI选关页_第七关_刷新预览(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        目标玩家: "实体",
        目标关卡: "整数",
    ) -> None:
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        元件ID表1: "元件ID列表" = 获取自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示元件ID_1,
        )
        元件ID表2: "元件ID列表" = 获取自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示元件ID_2,
        )
        位置偏移表: "三维向量列表" = 获取自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示位置偏移,
        )
        第二元件偏移表: "三维向量列表" = 获取自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到第二元件自带偏移,
        )
        旋转表1: "三维向量列表" = 获取自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示旋转_1,
        )
        旋转表2: "三维向量列表" = 获取自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示旋转_2,
        )

        旧预览实体1: "实体" = 获取自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_预览实体1)
        旧预览实体2: "实体" = 获取自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_预览实体2)
        销毁实体(self.game, 目标实体=旧预览实体1)
        销毁实体(self.game, 目标实体=旧预览实体2)
        设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_预览实体1, 变量值=0, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_预览实体2, 变量值=0, 是否触发事件=False)

        if 目标关卡 == 0:
            设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_预览关卡, 变量值=0, 是否触发事件=False)
            return

        列表序号: "整数" = (目标关卡 - 1)
        本地位置偏移: "三维向量" = 位置偏移表[列表序号]
        预览旋转1: "三维向量" = 旋转表1[列表序号]
        预览旋转2: "三维向量" = 旋转表2[列表序号]
        玩家位置: "三维向量"
        玩家旋转占位: "三维向量"
        玩家位置, 玩家旋转占位 = 获取实体位置与旋转(self.game, 目标实体=目标玩家)
        固定上抬偏移: "三维向量" = 创建三维向量(self.game, X分量=0.0, Y分量=0.0, Z分量=5.0)
        基准位置: "三维向量" = 三维向量加法(self.game, 三维向量1=玩家位置, 三维向量2=固定上抬偏移)
        目标位置1: "三维向量" = 三维向量加法(self.game, 三维向量1=基准位置, 三维向量2=本地位置偏移)

        预览元件ID1: "元件ID" = 元件ID表1[列表序号]
        预览实体1: "实体" = 创建元件(
            self.game,
            元件ID=预览元件ID1,
            位置=目标位置1,
            旋转=预览旋转1,
            拥有者实体=关卡实体,
            是否覆写等级=False,
            等级=1,
            单位标签索引列表=(),
        )
        设置自定义变量(
            self.game,
            目标实体=目标玩家,
            变量名=玩家变量_预览实体1,
            变量值=预览实体1,
            是否触发事件=False,
        )
        设置自定义变量(
            self.game,
            目标实体=目标玩家,
            变量名=玩家变量_预览关卡,
            变量值=目标关卡,
            是否触发事件=False,
        )

        预览元件ID2: "元件ID" = 元件ID表2[列表序号]
        空元件ID: "元件ID" = 0
        if 预览元件ID2 == 空元件ID:
            return
        本地自带偏移: "三维向量" = 第二元件偏移表[列表序号]
        目标位置2: "三维向量" = 三维向量加法(self.game, 三维向量1=基准位置, 三维向量2=本地自带偏移)

        预览实体2: "实体" = 创建元件(
            self.game,
            元件ID=预览元件ID2,
            位置=目标位置2,
            旋转=预览旋转2,
            拥有者实体=关卡实体,
            是否覆写等级=False,
            等级=1,
            单位标签索引列表=(),
        )
        设置自定义变量(
            self.game,
            目标实体=目标玩家,
            变量名=玩家变量_预览实体2,
            变量值=预览实体2,
            是否触发事件=False,
        )
        return

    def on_UI选关页_第七关_清空全员预览(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
    ) -> None:
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
        for p in 在场玩家列表:
            旧预览实体1: "实体" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_预览实体1)
            旧预览实体2: "实体" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_预览实体2)
            销毁实体(self.game, 目标实体=旧预览实体1)
            销毁实体(self.game, 目标实体=旧预览实体2)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_预览实体1, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_预览实体2, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_预览关卡, 变量值=0, 是否触发事件=False)
        return

    def on_第七关_回合推进派发(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        是否最后回合: "整数",
    ) -> None:
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        # 只在“结算阶段(3)”响应回合推进；一旦进入“推进中(4)”就忽略后续派发/点击，
        # 避免“自动推进后玩家仍可点击继续”在待办锁已清空时再次推进，导致剩余亲戚跳变（如 10→8）。
        当前阶段: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段)
        if 当前阶段 == 3:
            pass
        else:
            return

        # 推进锁：若门流程待办尚未清空，说明已经有人触发了回合推进（避免“定时器到点 + 手动继续”双触发推进两次）。
        待办锁: "字符串" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办)
        if 待办锁 == "无":
            pass
        else:
            return

        # 标记推进中：直到下一回合数据下发并进入进场阶段前，都不允许再次推进。
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段, 变量值=4, 是否触发事件=False)

        当前回合: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号)
        总回合: "整数" = 获取节点图变量(self.game, 变量名="总回合数")
        下一回合: "整数" = (当前回合 + 1)
        本次为最后回合: "布尔值" = 下一回合 > 总回合

        # 先写入门待办作为推进锁（避免双触发导致回合序号被递增两次）
        if 本次为最后回合:
            待办: "字符串" = "进入结算"
        else:
            待办: "字符串" = "下一回合"
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办, 变量值=待办, 是否触发事件=False)

        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号, 变量值=下一回合, 是否触发事件=False)

        # 顶栏右上角：剩余亲戚（UI房间_文本：由 HTML 拼接 current / total）
        room_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI房间_文本")
        diff: "整数" = (总回合 - 下一回合)
        剩余_raw: "整数" = (diff + 1)
        剩余: "整数" = max(0, 剩余_raw)
        剩余文本: "字符串" = str(剩余)
        总回合文本: "字符串" = str(总回合)
        room_text["剩余亲戚_当前"] = 剩余文本
        room_text["剩余亲戚_总"] = 总回合文本

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
        for p in 在场玩家列表:
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择, 变量值=0, 是否触发事件=False)

        result组: "整数" = 揭晓遮罩_result组
        for p in 在场玩家列表:
            修改界面布局内界面控件状态(self.game, p, result组, "界面控件组状态_关闭")

        dlg_show组: "整数" = 对白框_show组
        for p in 在场玩家列表:
            修改界面布局内界面控件状态(self.game, p, dlg_show组, "界面控件组状态_关闭")

        发送信号(self.game, 信号名=信号名_门动作, 目标状态="关闭")
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

        # 进入倒计时：3 -> 2 -> 1 -> 0，结束后按锁定模式执行（enter_level / settle）
        if 定时器名称 == 定时器名_进入倒计时:
            已过去: "整数" = 定时器序列序号
            总秒: "整数" = 获取节点图变量(self.game, 变量名="进入倒计时秒数")
            剩余: "整数" = (总秒 - 已过去)
            vote_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_投票")
            剩余文本: "字符串" = str(剩余)
            vote_map["countdown_sec"] = 剩余文本
            # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量

            if 剩余 == 0:
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时)
                locked_mode: "字符串" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式)
                locked_level: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_目标关卡)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_进行中, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式, 变量值="无", 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_目标关卡, 变量值=0, 是否触发事件=False)
                if locked_mode == "settle":
                    # 结算投票：将所有在场玩家设置为胜利并触发关卡结算
                    发送信号(self.game, 信号名=信号名_清空全员预览)
                    for p in 在场玩家列表:
                        设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票结算, 变量值=0, 是否触发事件=False)
                        设置玩家结算成功状态(self.game, 玩家实体=p, 结算状态="胜利")
                    结算关卡(self.game)
                    return
                # 确认进入关卡：广播“开始关卡”信号（参数：第X关）
                发送信号(self.game, 信号名="关卡大厅_开始关卡", 第X关=locked_level)
                发送信号(self.game, 信号名=信号名_清空全员预览)
                for p in 在场玩家列表:
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票关卡, 变量值=0, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票结算, 变量值=0, 是否触发事件=False)

                # 仅第七关：选关页负责切换到第七关-游戏中布局；其它关卡由各自的开始关卡监听方处理 UI/传送等。
                if locked_level == 7:
                    布局索引_游戏中: "整数" = 获取节点图变量(self.game, 变量名="布局索引_第七关游戏中")
                    if 布局索引_游戏中 == 0:
                        return
                    for p in 在场玩家列表:
                        切换当前界面布局(self.game, 目标玩家=p, 布局索引=布局索引_游戏中)
                    return

                # 非第七关：恢复选关页交互状态（避免停留在选关页时仍被遮罩/禁用态锁死）
                overlay_show: "整数" = 投票遮罩_show组
                vote_btn_enabled: "整数" = 投票按钮_enabled组
                vote_btn_disabled: "整数" = 投票按钮_disabled组
                关卡列表: "整数列表" = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
                for p in 在场玩家列表:
                    修改界面布局内界面控件状态(self.game, p, overlay_show, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, vote_btn_disabled, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, vote_btn_enabled, "界面控件组状态_开启")

                    sel_level: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名="ui_sel_level")
                    for lv in 关卡列表:
                        未选组: "整数" = 关卡号到未选组映射[lv]
                        已选组: "整数" = 关卡号到已选组映射[lv]
                        禁用组: "整数" = 关卡号到禁用组映射[lv]
                        if (sel_level != 0) and (lv == sel_level):
                            修改界面布局内界面控件状态(self.game, p, 未选组, "界面控件组状态_关闭")
                            修改界面布局内界面控件状态(self.game, p, 已选组, "界面控件组状态_开启")
                            修改界面布局内界面控件状态(self.game, p, 禁用组, "界面控件组状态_关闭")
                        else:
                            修改界面布局内界面控件状态(self.game, p, 已选组, "界面控件组状态_关闭")
                            修改界面布局内界面控件状态(self.game, p, 未选组, "界面控件组状态_开启")
                            修改界面布局内界面控件状态(self.game, p, 禁用组, "界面控件组状态_关闭")
                return
            return

        # 投票取消提示：到时隐藏
        if 定时器名称 == 定时器名_投票取消提示:
            show: "整数" = 投票取消提示_show组
            for p in 在场玩家列表:
                修改界面布局内界面控件状态(self.game, p, show, "界面控件组状态_关闭")
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_投票取消提示)
            return

        # 结算提示：到时隐藏
        if 定时器名称 == 定时器名_结算提示:
            show: "整数" = 结算提示_show组
            for p in 在场玩家列表:
                修改界面布局内界面控件状态(self.game, p, show, "界面控件组状态_关闭")
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示)
            return

        # 通关 UI 同步：到时隐藏/显示通关印章（延迟等待选关面板就绪）
        if 定时器名称 == 定时器名_通关UI同步:
            关卡列表: "整数列表" = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

            通关Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="关卡号到通关Key")
            通关表: "字符串_整数字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_列表")

            for p in 在场玩家列表:
                for lv in 关卡列表:
                    通关Key: "字符串" = 通关Key表[lv]
                    cleared: "整数" = 通关表[通关Key]
                    show组: "整数" = 关卡号到通关标记_show组[lv]
                    if cleared == 1:
                        修改界面布局内界面控件状态(self.game, p, show组, "界面控件组状态_开启")
                    else:
                        修改界面布局内界面控件状态(self.game, p, show组, "界面控件组状态_关闭")

            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_通关UI同步)
            return

        return

    def register_handlers(self):
        self.game.register_event_handler(
            "定时器触发时",
            self.on_定时器触发时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "关卡大厅_前往选关",
            self.on_关卡大厅_前往选关,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "UI选关页_第七关_刷新预览",
            self.on_UI选关页_第七关_刷新预览,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "UI选关页_第七关_清空全员预览",
            self.on_UI选关页_第七关_清空全员预览,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_回合推进派发",
            self.on_第七关_回合推进派发,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

