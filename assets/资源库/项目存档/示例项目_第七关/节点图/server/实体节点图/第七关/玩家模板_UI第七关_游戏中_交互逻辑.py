"""
graph_id: server_test_project_level7_ingame_controller
graph_name: 玩家模板_UI第七关_游戏中_交互逻辑
graph_type: server
description: 配套 `管理配置/UI源码/第七关-游戏中.html` 的交互与比赛闭环（选关进入 → 多回合 → 结算页 → 返回选关）：

- 主要交互：
  - allow/reject（btn_allow/btn_reject）：记录玩家本回合选择，并刷新审判庭状态。
  - 对话（btn_dialogue）：从“数据服务下发的对白列表”按序写回到 `UI战斗_文本.对话`（循环播放，不再随机）。
  - 顶部按钮：
    - 退出（btn_exit）：立即返回选关页（同时终止本关卡 UI 定时器）。
    - 关卡选择（btn_level_select）：同上，返回选关页。
- 回合状态机（UI 演示版）：
  - 进场 5 秒 → 投票（倒计时结束则**未操作默认允许并立即揭晓**；否则等待本轮**所有玩家完成选择**后揭晓）→ 结果态 4 秒（或手动继续）→ 下一回合
  - 达到总回合数后切换到结算页布局（第七关-结算.html）。
- 挂载实体：玩家实体（每个在场玩家各挂一份；`界面控件组触发时` 仅玩家图可接收）。

本文件已合并以下玩家侧节点图逻辑（减少挂载数量，保持行为一致）：
- `玩家模板_UI第七关_结算_交互逻辑`：结算页按钮与榜单写回、自动返回定时器回调。
- `玩家模板_第七关_音效播放`：监听信号 `第七关_播放2D音效(音效资产索引=整数)` 并对本玩家播放 2D 音效。

（Cursor `afterFileEdit` hook 会在编辑后触发 `validate-file` 校验。）
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

玩家变量_新手教程步骤: "字符串" = "ui_tut_step"  # 0=背景故事（guide_0），1~6=指引，7=完成页
玩家变量_新手教程完成: "字符串" = "ui_tut_done"  # 0/1

定时器名_进场倒计时: "字符串" = "ui_battle_entry_phase"
定时器名_回合倒计时: "字符串" = "ui_battle_stage_countdown"
定时器名_结算停留: "字符串" = "ui_battle_settlement_hold"
定时器名_新手教程倒计时: "字符串" = "ui_battle_tutorial_countdown"
定时器名_结算页自动返回: "字符串" = "ui_level7_result_auto_return"

关卡变量_门关闭完成后待办: "字符串" = "第七关_门_关闭完成后待办"
关卡变量_本回合真相为允许: "字符串" = "第七关_本回合_真相为允许"
关卡变量_本回合是否小孩: "字符串" = "第七关_本回合_是否小孩"

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
# 2D 音效
# 帮助切换音效：随机 30001~30003（用 30001 + 随机(0~2) 计算）
音效_拒绝: "整数" = 50047
音效_允许: "整数" = 50411

# ---------------------------- 门流程（信号驱动；门动作由独立门控制图负责） ----------------------------
信号名_门动作: "字符串" = "第七关_门_动作"
信号名_结算派发: "字符串" = "第七关_结算派发"
信号名_回合推进派发: "字符串" = "第七关_回合推进派发"

# UI 控件/状态组占位符：写回阶段会解析为真实整数索引，不会以字符串落库。
按钮索引_btn_allow: "整数" = "ui_key:第七关-游戏中_html__btn_allow__enabled__btn_item"
按钮索引_btn_reject: "整数" = "ui_key:第七关-游戏中_html__btn_reject__enabled__btn_item"
按钮索引_btn_dialogue: "整数" = "ui_key:第七关-游戏中_html__btn_dialogue__enabled__btn_item"
按钮索引_btn_exit: "整数" = "ui_key:第七关-游戏中_html__btn_exit__rect"
按钮索引_btn_level_select: "整数" = "ui_key:第七关-游戏中_html__btn_level_select__btn_item"
按钮索引_btn_help: "整数" = "ui_key:第七关-游戏中_html__btn_help__show__btn_item"
按钮索引_btn_tutorial_next_guide_0: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__guide_0__btn_item"
按钮索引_btn_tutorial_next_guide_1: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__guide_1__btn_item"
按钮索引_btn_tutorial_next_guide_2: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__guide_2__btn_item"
按钮索引_btn_tutorial_next_guide_3: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__guide_3__btn_item"
按钮索引_btn_tutorial_next_guide_4: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__guide_4__btn_item"
按钮索引_btn_tutorial_next_guide_5: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__guide_5__btn_item"
按钮索引_btn_tutorial_next_guide_6: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__guide_6__btn_item"
按钮索引_btn_tutorial_next_done: "整数" = "ui_key:第七关-游戏中_html__btn_tutorial_next__done__btn_item"
按钮索引_btn_reveal_close_result: "整数" = "ui_key:第七关-游戏中_html__btn_reveal_close_result__result__btn_item"
允许按钮_enabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_allow_state__enabled__group"
允许按钮_disabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_allow_state__disabled__group"
拒绝按钮_enabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_reject_state__enabled__group"
拒绝按钮_disabled组: "整数" = "ui_key:UI_STATE_GROUP__btn_reject_state__disabled__group"
揭晓遮罩_result组: "整数" = "ui_key:UI_STATE_GROUP__battle_settlement_overlay__result__group"
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

# 结算页 UI 控件占位符：写回阶段会解析为真实整数索引，不会以字符串落库。
结算按钮索引_btn_back: "整数" = "ui_key:第七关-结算_html__btn_back__btn_item"
结算按钮索引_btn_exit: "整数" = "ui_key:第七关-结算_html__btn_exit__rect"
结算按钮索引_btn_level_select: "整数" = "ui_key:第七关-结算_html__btn_level_select__btn_item"

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    # ---------------------------- 布局索引（由项目配置/写回阶段回填） ----------------------------
    GraphVariableConfig(
        name="布局索引_选关页",
        variable_type="整数",
        default_value=0,
        description="UI布局索引：选关页（关卡大厅-选关界面.html）。默认 0；写回阶段会尝试用 ui_guid_registry 的 LAYOUT_INDEX__HTML__关卡大厅-选关界面 自动回填。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="布局索引_第七关游戏中",
        variable_type="整数",
        default_value=0,
        description="UI布局索引：第七关游戏中页（第七关-游戏中.html）。默认 0；写回阶段会尝试用 ui_guid_registry 的 LAYOUT_INDEX__HTML__第七关-游戏中 自动回填。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="布局索引_结算页",
        variable_type="整数",
        default_value=0,
        description="UI布局索引：第七关结算页（第七关-结算.html）。默认 0；写回阶段会尝试用 ui_guid_registry 的 LAYOUT_INDEX__HTML__第七关-结算 自动回填。",
        is_exposed=False,
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
    # （本回合_对白列表 / 本回合_对白序号 / 当前阶段 / 已初始化 / 已广播开局信号 / 当前回合序号
    #   已迁移为关卡实体自定义变量，见文件头部 关卡变量_xxx 常量定义；
    #   门_关闭完成后待办 / 本回合_真相为允许 / 本回合_是否小孩 / 本回合_亲戚称谓 也由关卡实体自定义变量承载，
    #   结算参数（完整度/手办初始值/扣除值）、时间参数（进场/回合/结算/教程秒数）由各自使用的图管理。）
    GraphVariableConfig(
        name="总回合数",
        variable_type="整数",
        default_value=10,
        description="总回合数：达到后切换到结算页。",
        is_exposed=False,
    ),
    # ---------------------------- 结算页榜单 key 映射（避免在图逻辑中做字符串拼接/下标） ----------------------------
    GraphVariableConfig(
        name="榜单_slot到名次Key",
        variable_type="整数-字符串字典",
        default_value={1: "榜1名次", 2: "榜2名次", 3: "榜3名次", 4: "榜4名次"},
        description="slot(1~4)→UI结算_文本.<榜N名次> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="榜单_slot到名字Key",
        variable_type="整数-字符串字典",
        default_value={1: "榜1名", 2: "榜2名", 3: "榜3名", 4: "榜4名"},
        description="slot(1~4)→UI结算_文本.<榜N名> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="榜单_slot到标签Key",
        variable_type="整数-字符串字典",
        default_value={1: "榜1标签", 2: "榜2标签", 3: "榜3标签", 4: "榜4标签"},
        description="slot(1~4)→UI结算_文本.<榜N标签> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="榜单_slot到钱Key",
        variable_type="整数-字符串字典",
        default_value={1: "榜1钱", 2: "榜2钱", 3: "榜3钱", 4: "榜4钱"},
        description="slot(1~4)→UI结算_文本.<榜N钱> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="榜单_slot到钱前缀Key",
        variable_type="整数-字符串字典",
        default_value={1: "榜1钱前缀", 2: "榜2钱前缀", 3: "榜3钱前缀", 4: "榜4钱前缀"},
        description="slot(1~4)→UI结算_文本.<榜N钱前缀> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="榜单_slot到分Key",
        variable_type="整数-字符串字典",
        default_value={1: "榜1分", 2: "榜2分", 3: "榜3分", 4: "榜4分"},
        description="slot(1~4)→UI结算_文本.<榜N分> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="榜单_slot到分后缀Key",
        variable_type="整数-字符串字典",
        default_value={1: "榜1分后缀", 2: "榜2分后缀", 3: "榜3分后缀", 4: "榜4分后缀"},
        description="slot(1~4)→UI结算_文本.<榜N分后缀> key。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="临时_得分字典",
        variable_type="实体-整数字典",
        default_value={0: 0},
        description="内部：结算页用于构建并排序在场玩家得分的临时字典（实体→整数）。",
        is_exposed=False,
        dict_key_type="实体",
        dict_value_type="整数",
    ),
    # ---------------------------- 交互控件索引（ui_key 占位符口径） ----------------------------
    # overlay 继续按钮：位于 battle_settlement_overlay.result；该态仅包含一个可交互按钮，可直接按“状态组→btn_item”反查
    # ---------------------------- 多状态控件：底部操作按钮（allow/reject） ----------------------------
    # ---------------------------- 多状态控件：揭晓遮罩（使用稳定别名 UI_STATE_GROUP） ----------------------------
    # ---------------------------- 多状态控件：帮助按钮（hidden/show） ----------------------------
    # ---------------------------- 多状态控件：新手教程遮罩（tutorial_overlay） ----------------------------
    # ---------------------------- 多状态控件：新手教学倒计时（tutorial_countdown_state） ----------------------------
    # ---------------------------- 多状态控件：游戏区倒计时 badge（stage_countdown_state） ----------------------------
    # ---------------------------- 多状态控件：对白字幕框（stage_dialogue_state） ----------------------------
]

class 玩家模板_UI第七关_游戏中_交互逻辑:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # 说明：
    # - 公共信号监听与倒计时状态机已迁移到关卡实体单实例图：`关卡实体_第七关_UI游戏中_公共控制.py`
    # - 本图处理 UI 点击事件（`界面控件组触发时`）、结算页自动返回定时器（`定时器触发时`）与玩家侧音效信号。

    def on_第七关_播放2D音效(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        音效资产索引: "整数",
    ) -> None:
        玩家播放单次2D音效(
            self.game,
            目标实体=self.owner_entity,
            音效资产索引=音效资产索引,
            音量=音量_满,
            播放速度=播放速度_默认,
        )
        return

    def on_界面控件组触发时(self, 事件源实体: "实体", 事件源GUID: "GUID", 界面控件组组合索引, 界面控件组索引):
        目标玩家: "实体" = 事件源实体
        组索引: "整数" = 界面控件组索引
        # 统一口径：仅使用「界面控件组索引」。

        # ---------------------------- 结算页交互（合并：玩家模板_UI第七关_结算_交互逻辑） ----------------------------
        布局索引_结算页: "整数" = 获取节点图变量(self.game, 变量名="布局索引_结算页")
        if 布局索引_结算页 == 0:
            pass
        else:
            当前布局索引_结算: "整数" = 获取玩家当前界面布局(self.game, 玩家实体=目标玩家)
            if 当前布局索引_结算 == 布局索引_结算页:
                在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)

                # 写回榜单展示（完整度/手办存活与 progressbar 镜像标量由游戏中流程维护）
                关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
                result_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI结算_文本")

                名次Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到名次Key")
                名字Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到名字Key")
                标签Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到标签Key")
                钱Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到钱Key")
                钱前缀Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到钱前缀Key")
                分Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到分Key")
                分后缀Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到分后缀Key")

                # 榜单：按积分降序取前 4
                player_count: "整数" = len(在场玩家列表)
                p0: "实体" = 在场玩家列表[0]
                p0_pts: "整数" = 获取自定义变量(self.game, 目标实体=p0, 变量名=玩家变量_积分)
                score_dict_init: "实体-整数字典" = {p0: p0_pts}
                设置节点图变量(
                    self.game,
                    变量名="临时_得分字典",
                    变量值=score_dict_init,
                    是否触发事件=False,
                )

                score_dict_now: "实体-整数字典" = 获取节点图变量(self.game, 变量名="临时_得分字典")
                for p in 在场玩家列表:
                    pts: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
                    # 字典/列表为引用式：原地修改后无需再次设置节点图变量
                    score_dict_now[p] = pts

                score_dict_final: "实体-整数字典" = score_dict_now
                sorted_players, sorted_scores = 对字典按值排序(self.game, 字典=score_dict_final, 排序方式="排序规则_逆序")

                top1_p: "实体" = sorted_players[0]
                top1_pts: "整数" = sorted_scores[0]

                # slot1
                名次Key1: "字符串" = 名次Key表[1]
                名字Key1: "字符串" = 名字Key表[1]
                标签Key1: "字符串" = 标签Key表[1]
                钱Key1: "字符串" = 钱Key表[1]
                钱前缀Key1: "字符串" = 钱前缀Key表[1]
                分Key1: "字符串" = 分Key表[1]
                分后缀Key1: "字符串" = 分后缀Key表[1]
                top1_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top1_p)
                top1_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top1_p, 变量名=玩家变量_压岁钱)
                top1_money: "字符串" = str(top1_money_raw)
                top1_score: "字符串" = str(top1_pts)
                result_text[名次Key1] = "1"
                result_text[名字Key1] = top1_name
                result_text[标签Key1] = " "
                result_text[钱前缀Key1] = "¥ "
                result_text[钱Key1] = top1_money
                result_text[分Key1] = top1_score
                result_text[分后缀Key1] = " 积分"

                # slot2
                名次Key2: "字符串" = 名次Key表[2]
                名字Key2: "字符串" = 名字Key表[2]
                标签Key2: "字符串" = 标签Key表[2]
                钱Key2: "字符串" = 钱Key表[2]
                钱前缀Key2: "字符串" = 钱前缀Key表[2]
                分Key2: "字符串" = 分Key表[2]
                分后缀Key2: "字符串" = 分后缀Key表[2]
                if player_count >= 2:
                    top2_p: "实体" = sorted_players[1]
                    top2_pts: "整数" = sorted_scores[1]
                    top2_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top2_p)
                    top2_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top2_p, 变量名=玩家变量_压岁钱)
                    top2_money: "字符串" = str(top2_money_raw)
                    top2_score: "字符串" = str(top2_pts)
                    result_text[名次Key2] = "2"
                    result_text[名字Key2] = top2_name
                    result_text[标签Key2] = " "
                    result_text[钱前缀Key2] = "¥ "
                    result_text[钱Key2] = top2_money
                    result_text[分Key2] = top2_score
                    result_text[分后缀Key2] = " 积分"
                else:
                    result_text[名次Key2] = " "
                    result_text[名字Key2] = " "
                    result_text[标签Key2] = " "
                    result_text[钱前缀Key2] = " "
                    result_text[钱Key2] = " "
                    result_text[分Key2] = " "
                    result_text[分后缀Key2] = " "

                # slot3
                名次Key3: "字符串" = 名次Key表[3]
                名字Key3: "字符串" = 名字Key表[3]
                标签Key3: "字符串" = 标签Key表[3]
                钱Key3: "字符串" = 钱Key表[3]
                钱前缀Key3: "字符串" = 钱前缀Key表[3]
                分Key3: "字符串" = 分Key表[3]
                分后缀Key3: "字符串" = 分后缀Key表[3]
                if player_count >= 3:
                    top3_p: "实体" = sorted_players[2]
                    top3_pts: "整数" = sorted_scores[2]
                    top3_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top3_p)
                    top3_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top3_p, 变量名=玩家变量_压岁钱)
                    top3_money: "字符串" = str(top3_money_raw)
                    top3_score: "字符串" = str(top3_pts)
                    result_text[名次Key3] = "3"
                    result_text[名字Key3] = top3_name
                    result_text[标签Key3] = " "
                    result_text[钱前缀Key3] = "¥ "
                    result_text[钱Key3] = top3_money
                    result_text[分Key3] = top3_score
                    result_text[分后缀Key3] = " 积分"
                else:
                    result_text[名次Key3] = " "
                    result_text[名字Key3] = " "
                    result_text[标签Key3] = " "
                    result_text[钱前缀Key3] = " "
                    result_text[钱Key3] = " "
                    result_text[分Key3] = " "
                    result_text[分后缀Key3] = " "

                # slot4
                名次Key4: "字符串" = 名次Key表[4]
                名字Key4: "字符串" = 名字Key表[4]
                标签Key4: "字符串" = 标签Key表[4]
                钱Key4: "字符串" = 钱Key表[4]
                钱前缀Key4: "字符串" = 钱前缀Key表[4]
                分Key4: "字符串" = 分Key表[4]
                分后缀Key4: "字符串" = 分后缀Key表[4]
                if player_count >= 4:
                    top4_p: "实体" = sorted_players[3]
                    top4_pts: "整数" = sorted_scores[3]
                    top4_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top4_p)
                    top4_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top4_p, 变量名=玩家变量_压岁钱)
                    top4_money: "字符串" = str(top4_money_raw)
                    top4_score: "字符串" = str(top4_pts)
                    result_text[名次Key4] = "4"
                    result_text[名字Key4] = top4_name
                    result_text[标签Key4] = " "
                    result_text[钱前缀Key4] = "¥ "
                    result_text[钱Key4] = top4_money
                    result_text[分Key4] = top4_score
                    result_text[分后缀Key4] = " 积分"
                else:
                    result_text[名次Key4] = " "
                    result_text[名字Key4] = " "
                    result_text[标签Key4] = " "
                    result_text[钱前缀Key4] = " "
                    result_text[钱Key4] = " "
                    result_text[分Key4] = " "
                    result_text[分后缀Key4] = " "
                # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量

                btn_back: "整数" = 结算按钮索引_btn_back
                btn_level_select: "整数" = 结算按钮索引_btn_level_select

                # 顶部：退出/关卡选择 → 选关页
                触发顶部返回: "布尔值" = (
                    (组索引 == 结算按钮索引_btn_exit)
                    or (组索引 == btn_level_select)
                )
                # 结算页只保留『返回大厅』：返回只负责切回选关并终止结算页定时器。
                # 开局 Reset+Init 由关卡实体公共控制图在收到『关卡大厅_开始关卡(第X关=7)』时无条件执行。
                触发返回大厅: "布尔值" = 触发顶部返回 or (组索引 == btn_back)
                if 触发返回大厅:
                    sfx_idx: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
                    sfx_id: "整数" = (30001 + sfx_idx)
                    玩家播放单次2D音效(
                        self.game,
                        目标实体=目标玩家,
                        音效资产索引=sfx_id,
                        音量=音量_满,
                        播放速度=播放速度_默认,
                    )

                    布局索引_选关: "整数" = 获取节点图变量(self.game, 变量名="布局索引_选关页")
                    if 布局索引_选关 == 0:
                        return
                    for p in 在场玩家列表:
                        终止定时器(self.game, 目标实体=p, 定时器名称=定时器名_结算页自动返回)
                        切换当前界面布局(self.game, 目标玩家=p, 布局索引=布局索引_选关)
                    return

                return

        # 仅当玩家当前处于“第七关-游戏中”布局时才处理（避免其它界面控件触发导致本图误写回/误推进）
        布局索引_游戏中: "整数" = 获取节点图变量(self.game, 变量名="布局索引_第七关游戏中")
        当前布局索引: "整数" = 获取玩家当前界面布局(self.game, 玩家实体=目标玩家)
        # 写回阶段未回填布局索引时（布局索引==0）：保持旧行为（不做布局过滤）。
        需要拦截: "布尔值" = (布局索引_游戏中 != 0) and (当前布局索引 != 布局索引_游戏中)
        if 需要拦截:
            return

        投票阶段: "整数" = 2
        结算阶段: "整数" = 3

        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        当前阶段: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前阶段)
        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
        教程页状态组列表: "整数列表" = [
            新手教程_guide_0组,
            新手教程_guide_1组,
            新手教程_guide_2组,
            新手教程_guide_3组,
            新手教程_guide_4组,
            新手教程_guide_5组,
            新手教程_guide_6组,
            新手教程_done组,
            新手教程_wait_others组,
        ]
        教程按钮到步骤: "整数-整数字典" = {
            按钮索引_btn_tutorial_next_guide_0: 1,
            按钮索引_btn_tutorial_next_guide_1: 2,
            按钮索引_btn_tutorial_next_guide_2: 3,
            按钮索引_btn_tutorial_next_guide_3: 4,
            按钮索引_btn_tutorial_next_guide_4: 5,
            按钮索引_btn_tutorial_next_guide_5: 6,
            按钮索引_btn_tutorial_next_guide_6: 7,
        }
        教程步骤到状态组: "整数-整数字典" = {
            1: 新手教程_guide_1组,
            2: 新手教程_guide_2组,
            3: 新手教程_guide_3组,
            4: 新手教程_guide_4组,
            5: 新手教程_guide_5组,
            6: 新手教程_guide_6组,
            7: 新手教程_done组,
        }

        # 顶部：退出/关卡选择 → 返回选关
        触发返回选关: "布尔值" = (
            (组索引 == 按钮索引_btn_exit)
            or (组索引 == 按钮索引_btn_level_select)
        )
        if 触发返回选关:
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进场倒计时)
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_回合倒计时)
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算停留)
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_新手教程倒计时)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办, 变量值="无", 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合真相为允许, 变量值=True, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合是否小孩, 变量值=False, 是否触发事件=False)

            # 退出本关卡时：清理当前回合生成的“亲戚”实体，避免场上残留
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

            布局索引_选关页: "整数" = 获取节点图变量(self.game, 变量名="布局索引_选关页")
            if 布局索引_选关页 == 0:
                return
            for p in 在场玩家列表:
                切换当前界面布局(self.game, 目标玩家=p, 布局索引=布局索引_选关页)
            return

        # 新手教程：下一步/完成（tutorial_overlay 每个状态的『下一步』按钮 GUID 不同，按按钮索引映射到“下一页”）
        触发教程下一步: "布尔值" = (
            (组索引 == 按钮索引_btn_tutorial_next_guide_0)
            or (组索引 == 按钮索引_btn_tutorial_next_guide_1)
            or (组索引 == 按钮索引_btn_tutorial_next_guide_2)
            or (组索引 == 按钮索引_btn_tutorial_next_guide_3)
            or (组索引 == 按钮索引_btn_tutorial_next_guide_4)
            or (组索引 == 按钮索引_btn_tutorial_next_guide_5)
            or (组索引 == 按钮索引_btn_tutorial_next_guide_6)
            or (组索引 == 按钮索引_btn_tutorial_next_done)
        )
        if 触发教程下一步:
            # 帮助切换音效：随机一个（30001/30002/30003）
            sfx_idx: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
            sfx_id: "整数" = (30001 + sfx_idx)
            玩家播放单次2D音效(
                self.game,
                目标实体=目标玩家,
                音效资产索引=sfx_id,
                音量=音量_满,
                播放速度=播放速度_默认,
            )

            # 教程页切换顺序：先开目标页，再关其它页（避免出现“先全关→中间空态→再开启”的瞬态）
            if 组索引 == 按钮索引_btn_tutorial_next_done:
                # done 页点击『完成』：
                # - 开局前（当前阶段==0 且 未广播开局信号）：标记完成 → 展示 wait_others → 统计人数；全员完成则提前广播开局信号
                # - 开局后（已广播开局信号）：视为个人回顾结束（关闭遮罩）
                if 当前阶段 == 0:
                    # 注意：正式开局信号《第七关_开始游戏》触发后，到第一位亲戚数据《第七关_下发亲戚数据》到来前，
                    # 当前阶段仍可能保持 0。此时玩家点帮助回顾，再点“完成”不应进入 wait_others。
                    已广播开局信号: "布尔值" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号)
                    if 已广播开局信号:
                        # 个人回顾结束：关闭所有教程页
                        for 教程页状态组 in 教程页状态组列表:
                            修改界面布局内界面控件状态(self.game, 目标玩家, 教程页状态组, "界面控件组状态_关闭")
                        return
                    else:
                        pass

                    设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_新手教程完成, 变量值=1, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_新手教程步骤, 变量值=7, 是否触发事件=False)

                    # 展示“等待其他玩家”页（倒计时与完成度在 UI战斗_整数 内刷新）
                    # 先开目标页，再关其它页（包含 done）
                    修改界面布局内界面控件状态(self.game, 目标玩家, 新手教程_wait_others组, "界面控件组状态_开启")
                    for 教程页状态组 in 教程页状态组列表:
                        if 教程页状态组 == 新手教程_wait_others组:
                            pass
                        else:
                            修改界面布局内界面控件状态(self.game, 目标玩家, 教程页状态组, "界面控件组状态_关闭")

                    # 统计完成度：按玩家自定义变量 ui_tut_done 计数
                    已完成: "整数" = 0
                    for p in 在场玩家列表:
                        done_val: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_新手教程完成)
                        if done_val == 1:
                            已完成 = (已完成 + 1)

                    总人数: "整数" = len(在场玩家列表)
                    battle_int: "字符串_整数字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_整数")
                    battle_int["新手教程_已完成人数"] = 已完成
                    if 已完成 == 总人数:
                        battle_int["新手教程_剩余秒"] = 0
                    # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量

                    # 全员完成 → 提前开局（与倒计时到 0 的口径一致）
                    if 已完成 == 总人数:
                        已广播开局信号: "布尔值" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号)
                        if 已广播开局信号:
                            return
                        else:
                            pass

                        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_已广播开局信号, 变量值=True, 是否触发事件=False)
                        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_新手教程倒计时)
                        发送信号(self.game, 信号名="第七关_开始游戏")
                        return
                    else:
                        return
                else:
                    # 开局后：个人回顾结束（关闭遮罩）
                    for 教程页状态组 in 教程页状态组列表:
                        修改界面布局内界面控件状态(self.game, 目标玩家, 教程页状态组, "界面控件组状态_关闭")
                    return
            else:
                下一步: "整数" = 教程按钮到步骤[组索引]
                目标教程页状态组: "整数" = 教程步骤到状态组[下一步]
                设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_新手教程步骤, 变量值=下一步, 是否触发事件=False)

                # 先开目标页，再关其它页（包含当前页）
                修改界面布局内界面控件状态(self.game, 目标玩家, 目标教程页状态组, "界面控件组状态_开启")
                for 教程页状态组 in 教程页状态组列表:
                    if 教程页状态组 == 目标教程页状态组:
                        pass
                    else:
                        修改界面布局内界面控件状态(self.game, 目标玩家, 教程页状态组, "界面控件组状态_关闭")
                return

        # 帮助：给出即时反馈（写回对白）
        触发帮助: "布尔值" = 组索引 == 按钮索引_btn_help
        if 触发帮助:
            # 帮助切换音效：随机一个（打开“回顾教程”也视为切换）
            sfx_idx: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
            sfx_id: "整数" = (30001 + sfx_idx)
            玩家播放单次2D音效(
                self.game,
                目标实体=目标玩家,
                音效资产索引=sfx_id,
                音量=音量_满,
                播放速度=播放速度_默认,
            )

            battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")
            battle_text["对话"] = "提示：先点击『对话』获取线索，再在投票阶段选择『允许/拒绝』。"

            # 帮助提示属于“说话内容”，这里直接展示对白框（玩家个人）
            修改界面布局内界面控件状态(self.game, 目标玩家, 对白框_show组, "界面控件组状态_开启")

            # 同时打开新手教程回顾（从 guide_0 开始：先背景故事，再进入指引）
            # 帮助回顾属于玩家个人：强制隐藏“开局倒计时”（避免倒计时与回顾混在一起）
            # 先开目标页（guide_0），再关其它页（避免“先全关→空态→再开启”的瞬态）
            修改界面布局内界面控件状态(self.game, 目标玩家, 新手教程_guide_0组, "界面控件组状态_开启")
            for 教程页状态组 in 教程页状态组列表:
                if 教程页状态组 == 新手教程_guide_0组:
                    pass
                else:
                    修改界面布局内界面控件状态(self.game, 目标玩家, 教程页状态组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, 目标玩家, 新手教程倒计时_show组, "界面控件组状态_关闭")
            设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_新手教程步骤, 变量值=0, 是否触发事件=False)
            return

        # 对话：无限点击，写回 UI战斗_文本.对话
        触发对话: "布尔值" = 组索引 == 按钮索引_btn_dialogue
        if 触发对话:
            台词列表: "字符串列表" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合_对白列表)
            idx: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合_对白序号)
            total: "整数" = len(台词列表)
            need_wrap: "布尔值" = (idx >= total)
            if need_wrap:
                idx2: "整数" = 0
            else:
                idx2: "整数" = idx
            台词: "字符串" = 台词列表[idx2]

            # 首次点击“对话”后才展示对白框（黑底黑边）
            修改界面布局内界面控件状态(self.game, 目标玩家, 对白框_show组, "界面控件组状态_开启")

            battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")
            battle_text["对话"] = 台词
            next_i: "整数" = (idx2 + 1)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合_对白序号, 变量值=next_i, 是否触发事件=False)
            return

        # allow / reject：仅在投票阶段生效
        触发允许: "布尔值" = 组索引 == 按钮索引_btn_allow
        触发拒绝: "布尔值" = 组索引 == 按钮索引_btn_reject
        触发投票按钮: "布尔值" = 触发允许 or 触发拒绝
        if 触发投票按钮:
            if 当前阶段 == 投票阶段:
                if 触发允许:
                    投票值: "整数" = 1
                    投票音效: "整数" = 音效_允许
                else:
                    投票值: "整数" = 2
                    投票音效: "整数" = 音效_拒绝

                玩家播放单次2D音效(
                    self.game,
                    目标实体=目标玩家,
                    音效资产索引=投票音效,
                    音量=音量_满,
                    播放速度=播放速度_默认,
                )
                设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_回合选择, 变量值=投票值, 是否触发事件=False)
                battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")

                # 刷新审判庭：按得分排名展示（同分按在场顺序稳定）
                slot_to_name_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到名字Key")
                slot_to_pts_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到分Key")
                slot_to_state_key: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="审判_slot到态Key")

                # 状态颜色：与 UI战斗_文本.审判N态 同步（用于 <color={1:lv.UI战斗_颜色.审判N态}>）
                style_colors: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI样式_颜色")
                c_thinking: "字符串" = style_colors["状态_思考中"]
                c_allow: "字符串" = style_colors["状态_允许"]
                c_reject: "字符串" = style_colors["状态_拒绝"]
                battle_color: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_颜色")

                # 得分排序：用于“按排名显示”
                player_count: "整数" = len(在场玩家列表)
                p0: "实体" = 在场玩家列表[0]
                p0_pts: "整数" = 获取自定义变量(self.game, 目标实体=p0, 变量名=玩家变量_积分)
                score_dict: "实体-整数字典" = {p0: p0_pts}
                for p in 在场玩家列表:
                    pts: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
                    score_dict[p] = pts

                sorted_players, sorted_scores = 对字典按值排序(self.game, 字典=score_dict, 排序方式="排序规则_逆序")

                # 顶栏：按当前第 1 名显示压岁钱/排名
                top_pts: "整数" = sorted_scores[0]
                battle_text["压岁钱"] = str(top_pts)
                battle_text["排名"] = "No. 1"

                slots: "整数列表" = [1, 2, 3, 4]
                for slot in slots:
                    name_key: "字符串" = slot_to_name_key[slot]
                    pts_key: "字符串" = slot_to_pts_key[slot]
                    state_key: "字符串" = slot_to_state_key[slot]
                    if player_count >= slot:
                        idx: "整数" = (slot - 1)
                        p: "实体" = sorted_players[idx]
                        pts: "整数" = sorted_scores[idx]
                        pts_text: "字符串" = str(pts)
                        nick: "字符串" = 获取玩家昵称(self.game, 玩家实体=p)
                        c: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择)
                        if c == 0:
                            st: "字符串" = "思考中"
                            st_color: "字符串" = c_thinking
                        elif c == 1:
                            st: "字符串" = "允许"
                            st_color = c_allow
                        else:
                            st: "字符串" = "拒绝"
                            st_color = c_reject
                        battle_text[name_key] = nick
                        battle_text[pts_key] = pts_text
                        battle_text[state_key] = st
                        battle_color[state_key] = st_color
                    else:
                        battle_text[name_key] = "—"
                        battle_text[pts_key] = "0"
                        if slot == 4:
                            battle_text[state_key] = " "
                        else:
                            battle_text[state_key] = " "
                        battle_color[state_key] = c_thinking
                修改界面布局内界面控件状态(self.game, 目标玩家, 允许按钮_enabled组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, 目标玩家, 允许按钮_disabled组, "界面控件组状态_开启")
                修改界面布局内界面控件状态(self.game, 目标玩家, 拒绝按钮_enabled组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, 目标玩家, 拒绝按钮_disabled组, "界面控件组状态_开启")
            else:
                return

        # 投票：当本轮所有玩家都完成选择后，立即揭晓并进入结果态
        本次投票发生: "布尔值" = (当前阶段 == 投票阶段) and 触发投票按钮
        if 本次投票发生:
            未选人数: "整数" = 0
            允许票: "整数" = 0
            拒绝票: "整数" = 0
            for p in 在场玩家列表:
                c: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择)
                if c == 0:
                    未选人数 = (未选人数 + 1)
                elif c == 1:
                    允许票 = (允许票 + 1)
                else:
                    拒绝票 = (拒绝票 + 1)

            if 未选人数 == 0:
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
                battle_text["回合倒计时"] = " "

                # 公共结算由关卡实体执行：通过信号参数传递票数。
                发送信号(self.game, 信号名=信号名_结算派发, 允许票=允许票, 拒绝票=拒绝票)
                return

            return

        # overlay：result 态『继续』→推进下一回合
        触发继续: "布尔值" = 组索引 == 按钮索引_btn_reveal_close_result
        if 触发继续:
            if 当前阶段 == 结算阶段:
                pass
            else:
                return

            # 玩家手动点击"继续"：直接触发公共回合推进，并终止结算停留定时器，
            # 避免“倒计时到点 + 手动点击”双触发导致推进两次。
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算停留)

            当前回合: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_当前回合序号)
            总回合: "整数" = 获取节点图变量(self.game, 变量名="总回合数")
            下一回合: "整数" = (当前回合 + 1)
            if 下一回合 > 总回合:
                最后一回合标记: "整数" = 1
            else:
                最后一回合标记: "整数" = 0
            发送信号(self.game, 信号名=信号名_回合推进派发, 是否最后回合=最后一回合标记)
            return

        return

    def on_定时器触发时(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        定时器名称: "字符串",
        定时器序列序号: "整数",
        循环次数: "整数",
    ) -> None:
        if 定时器名称 == 定时器名_结算页自动返回:
            pass
        else:
            return

        目标玩家: "实体" = self.owner_entity
        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
        首位玩家: "实体" = 在场玩家列表[0]
        if 目标玩家 == 首位玩家:
            pass
        else:
            return

        # 仅当玩家当前处于“结算页”布局时才处理（避免其它界面同名定时器误触发）
        布局索引_结算页: "整数" = 获取节点图变量(self.game, 变量名="布局索引_结算页")
        当前布局索引: "整数" = 获取玩家当前界面布局(self.game, 玩家实体=目标玩家)
        # 写回阶段未回填布局索引时（布局索引==0）：不做布局过滤（仅依赖“结算入场时启动的定时器”来触发）
        需要拦截: "布尔值" = (布局索引_结算页 != 0) and (当前布局索引 != 布局索引_结算页)
        if 需要拦截:
            return

        # 序号=1：进入结算页后首次刷新榜单（无需玩家点击）
        if 定时器序列序号 == 1:
            关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
            result_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI结算_文本")

            名次Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到名次Key")
            名字Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到名字Key")
            标签Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到标签Key")
            钱Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到钱Key")
            钱前缀Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到钱前缀Key")
            分Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到分Key")
            分后缀Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="榜单_slot到分后缀Key")

            player_count: "整数" = len(在场玩家列表)
            p0: "实体" = 在场玩家列表[0]
            p0_pts: "整数" = 获取自定义变量(self.game, 目标实体=p0, 变量名=玩家变量_积分)
            score_dict_init: "实体-整数字典" = {p0: p0_pts}
            设置节点图变量(
                self.game,
                变量名="临时_得分字典",
                变量值=score_dict_init,
                是否触发事件=False,
            )

            score_dict_now: "实体-整数字典" = 获取节点图变量(self.game, 变量名="临时_得分字典")
            for p in 在场玩家列表:
                pts: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
                score_dict_now[p] = pts

            score_dict_final: "实体-整数字典" = score_dict_now
            sorted_players, sorted_scores = 对字典按值排序(self.game, 字典=score_dict_final, 排序方式="排序规则_逆序")

            top1_p: "实体" = sorted_players[0]
            top1_pts: "整数" = sorted_scores[0]

            名次Key1: "字符串" = 名次Key表[1]
            名字Key1: "字符串" = 名字Key表[1]
            标签Key1: "字符串" = 标签Key表[1]
            钱Key1: "字符串" = 钱Key表[1]
            钱前缀Key1: "字符串" = 钱前缀Key表[1]
            分Key1: "字符串" = 分Key表[1]
            分后缀Key1: "字符串" = 分后缀Key表[1]
            top1_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top1_p)
            top1_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top1_p, 变量名=玩家变量_压岁钱)
            top1_money: "字符串" = str(top1_money_raw)
            top1_score: "字符串" = str(top1_pts)
            result_text[名次Key1] = "1"
            result_text[名字Key1] = top1_name
            result_text[标签Key1] = " "
            result_text[钱前缀Key1] = "¥ "
            result_text[钱Key1] = top1_money
            result_text[分Key1] = top1_score
            result_text[分后缀Key1] = " 积分"

            名次Key2: "字符串" = 名次Key表[2]
            名字Key2: "字符串" = 名字Key表[2]
            标签Key2: "字符串" = 标签Key表[2]
            钱Key2: "字符串" = 钱Key表[2]
            钱前缀Key2: "字符串" = 钱前缀Key表[2]
            分Key2: "字符串" = 分Key表[2]
            分后缀Key2: "字符串" = 分后缀Key表[2]
            if player_count >= 2:
                top2_p: "实体" = sorted_players[1]
                top2_pts: "整数" = sorted_scores[1]
                top2_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top2_p)
                top2_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top2_p, 变量名=玩家变量_压岁钱)
                top2_money: "字符串" = str(top2_money_raw)
                top2_score: "字符串" = str(top2_pts)
                result_text[名次Key2] = "2"
                result_text[名字Key2] = top2_name
                result_text[标签Key2] = " "
                result_text[钱前缀Key2] = "¥ "
                result_text[钱Key2] = top2_money
                result_text[分Key2] = top2_score
                result_text[分后缀Key2] = " 积分"
            else:
                result_text[名次Key2] = " "
                result_text[名字Key2] = " "
                result_text[标签Key2] = " "
                result_text[钱前缀Key2] = " "
                result_text[钱Key2] = " "
                result_text[分Key2] = " "
                result_text[分后缀Key2] = " "

            名次Key3: "字符串" = 名次Key表[3]
            名字Key3: "字符串" = 名字Key表[3]
            标签Key3: "字符串" = 标签Key表[3]
            钱Key3: "字符串" = 钱Key表[3]
            钱前缀Key3: "字符串" = 钱前缀Key表[3]
            分Key3: "字符串" = 分Key表[3]
            分后缀Key3: "字符串" = 分后缀Key表[3]
            if player_count >= 3:
                top3_p: "实体" = sorted_players[2]
                top3_pts: "整数" = sorted_scores[2]
                top3_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top3_p)
                top3_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top3_p, 变量名=玩家变量_压岁钱)
                top3_money: "字符串" = str(top3_money_raw)
                top3_score: "字符串" = str(top3_pts)
                result_text[名次Key3] = "3"
                result_text[名字Key3] = top3_name
                result_text[标签Key3] = " "
                result_text[钱前缀Key3] = "¥ "
                result_text[钱Key3] = top3_money
                result_text[分Key3] = top3_score
                result_text[分后缀Key3] = " 积分"
            else:
                result_text[名次Key3] = " "
                result_text[名字Key3] = " "
                result_text[标签Key3] = " "
                result_text[钱前缀Key3] = " "
                result_text[钱Key3] = " "
                result_text[分Key3] = " "
                result_text[分后缀Key3] = " "

            名次Key4: "字符串" = 名次Key表[4]
            名字Key4: "字符串" = 名字Key表[4]
            标签Key4: "字符串" = 标签Key表[4]
            钱Key4: "字符串" = 钱Key表[4]
            钱前缀Key4: "字符串" = 钱前缀Key表[4]
            分Key4: "字符串" = 分Key表[4]
            分后缀Key4: "字符串" = 分后缀Key表[4]
            if player_count >= 4:
                top4_p: "实体" = sorted_players[3]
                top4_pts: "整数" = sorted_scores[3]
                top4_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top4_p)
                top4_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top4_p, 变量名=玩家变量_压岁钱)
                top4_money: "字符串" = str(top4_money_raw)
                top4_score: "字符串" = str(top4_pts)
                result_text[名次Key4] = "4"
                result_text[名字Key4] = top4_name
                result_text[标签Key4] = " "
                result_text[钱前缀Key4] = "¥ "
                result_text[钱Key4] = top4_money
                result_text[分Key4] = top4_score
                result_text[分后缀Key4] = " 积分"
            else:
                result_text[名次Key4] = " "
                result_text[名字Key4] = " "
                result_text[标签Key4] = " "
                result_text[钱前缀Key4] = " "
                result_text[钱Key4] = " "
                result_text[分Key4] = " "
                result_text[分后缀Key4] = " "
            return

        # 序号!=1：到点自动返回选关（仅当入口图启动了第二个序列点；定时器序列序号=序列元素值）
        布局索引_选关: "整数" = 获取节点图变量(self.game, 变量名="布局索引_选关页")
        if 布局索引_选关 == 0:
            return
        for p in 在场玩家列表:
            终止定时器(self.game, 目标实体=p, 定时器名称=定时器名_结算页自动返回)
            切换当前界面布局(self.game, 目标玩家=p, 布局索引=布局索引_选关)
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "界面控件组触发时",
            self.on_界面控件组触发时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "定时器触发时",
            self.on_定时器触发时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_播放2D音效",
            self.on_第七关_播放2D音效,
            owner=self.owner_entity,
        )
        # 说明：本图仅保留 UI 点击入口；全局信号/定时器状态机已下沉到关卡实体图（避免广播信号在每个玩家实例重复执行）。

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))



