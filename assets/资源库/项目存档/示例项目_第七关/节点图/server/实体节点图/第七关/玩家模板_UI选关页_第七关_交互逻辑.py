"""
graph_id: server_test_project_ui_level_select_level7_controller
graph_name: 玩家模板_UI选关页_第七关_交互逻辑
graph_type: server
description: 配套 `管理配置/UI源码/关卡大厅-选关界面.html` 的交互闭环（第七关）：

- 选关列表：
  - 点击任意关卡按钮：切换该关卡为“选中(绿色)”并恢复上一次选中的关卡为“未选(黄色)”。
- 同步关卡预览：每个玩家刷新所选关卡的预览元件；切换关卡会先清理旧预览再创建新预览。
    - 预览由关卡实体图 `关卡实体_UI选关页_第七关_倒计时执行` 执行创建/清理：位置口径为“玩家当前位置 + (0,5,0) + 关卡位置偏移”。
    - 旧预览通过玩家自定义变量 `ui_preview_entity_1/ui_preview_entity_2` 存放预览元件实体引用（实体），刷新时直接销毁旧实体（真机侧创建元件通常没有可用 GUID）。
    - 双元件关卡（仅第 4/5/8 关）：第 2 个元件位置 = 展示基准位置（玩家当前位置 + (0,5,0)） + 第 2 元件偏移（相对展示基准位置）。
  - 点击底部 `投票此关`：按当前选中关卡发起投票，投票达成后进入对应关卡。
- 投票进入关卡：
  - 点击底部 `投票此关`：显示投票结果遮罩 `vote_overlay`，短倒计时后切换到 `第七关-游戏中.html` 对应布局。
  - 点击 `我拒绝`：关闭遮罩、恢复 `投票此关` 按钮为可点击，并短暂显示 `vote_cancel_tip` 提示。
- 进行结算：
  - 点击顶部 `进行结算`：发起“结算投票”（每人点击一次计 1 票，门槛为在场玩家过半）。
    - 达到门槛：显示 `vote_overlay` 并进入倒计时；倒计时结束后触发关卡结算（`结算关卡`）。
    - 点击 `我拒绝`：取消倒计时、清空所有人的投票并隐藏遮罩。
    - 顶部 `退出/关卡选择`：仅发送信号 `关卡大厅_前往选关`（前往/重置选关面板由大厅控制图统一处理）。

实现原则：
- UI 变量只写回 `UI选关_文本 / UI选关_投票`（与 HTML 占位符 `lv.UI选关_*` 对齐）。
- 多状态切换只通过 `UI_STATE_GROUP__<state_group>__<state>__group` 的稳定别名（避免依赖导出 ui_key 拼接细节）。
- 挂载实体：玩家实体（每个在场玩家各挂一份；`界面控件组触发时` 仅玩家图可接收）。

本文件已合并以下玩家侧节点图逻辑（减少挂载数量，保持行为一致）：
- `玩家模板_关卡大厅_实体创建_传送到选关站位`：玩家实体创建时写入 `ui_player_index` 并传送到选关站位。
- `玩家模板_关卡大厅_结算成功_监听胜利状态`：监听 `关卡大厅_结算成功`，仅将“自己”标记为胜利。
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

玩家变量_选中关卡: "字符串" = "ui_sel_level"
玩家变量_投票关卡: "字符串" = "ui_vote_level"
玩家变量_投票结算: "字符串" = "ui_vote_settle"
玩家变量_预览关卡: "字符串" = "ui_preview_level"
玩家变量_预览实体1: "字符串" = "ui_preview_entity_1"
玩家变量_预览实体2: "字符串" = "ui_preview_entity_2"
玩家变量_玩家序号: "字符串" = "ui_player_index"

定时器名_进入倒计时: "字符串" = "ui_level_select_enter_countdown"
定时器名_投票取消提示: "字符串" = "ui_level_select_vote_cancel_tip"
定时器名_结算提示: "字符串" = "ui_level_select_settle_tip"

信号名_刷新预览: "字符串" = "UI选关页_第七关_刷新预览"
信号名_清空全员预览: "字符串" = "UI选关页_第七关_清空全员预览"

# 跨图共享状态：投票倒计时锁通过关卡实体自定义变量协调（本图写入、倒计时执行图回调读取）
选关_投票倒计时_进行中: "字符串" = "选关_投票倒计时_进行中"
选关_投票倒计时_模式: "字符串" = "选关_投票倒计时_模式"
选关_投票倒计时_目标关卡: "字符串" = "选关_投票倒计时_目标关卡"

# 关卡实体自定义变量名：预览控制图通过这些键读取配置。
关卡实体自定义变量名_预览配置_关卡号到展示元件ID_1: "字符串" = "UI选关_预览_展示元件ID_1"
关卡实体自定义变量名_预览配置_关卡号到展示元件ID_2: "字符串" = "UI选关_预览_展示元件ID_2"
关卡实体自定义变量名_预览配置_关卡号到展示位置偏移: "字符串" = "UI选关_预览配置_关卡号到展示位置偏移"
关卡实体自定义变量名_预览配置_关卡号到第二元件自带偏移: "字符串" = "UI选关_预览_第二元件偏移"
关卡实体自定义变量名_预览配置_关卡号到展示旋转_1: "字符串" = "UI选关_预览配置_关卡号到展示旋转_1"
关卡实体自定义变量名_预览配置_关卡号到展示旋转_2: "字符串" = "UI选关_预览配置_关卡号到展示旋转_2"

音量_满: "整数" = 100
播放速度_默认: "浮点数" = 1.0

# 导航/切换音效：随机 30001~30003（用 30001 + 随机(0~2) 计算）
音效_拒绝: "整数" = 50047
音效_允许: "整数" = 50411

# UI 控件/状态组占位符：写回阶段会解析为真实整数索引，不会以字符串落库。
按钮索引_btn_exit: "整数" = "ui_key:关卡大厅-选关界面_html__btn_exit__rect"
按钮索引_btn_level_select: "整数" = "ui_key:关卡大厅-选关界面_html__btn_level_select__btn_item"
按钮索引_btn_settle: "整数" = "ui_key:关卡大厅-选关界面_html__btn_settle__btn_item"
按钮索引_rect_btn_start: "整数" = "ui_key:关卡大厅-选关界面_html__rect_btn_start__enabled__btn_item"
按钮索引_btn_vote_reject: "整数" = "ui_key:关卡大厅-选关界面_html__btn_vote_reject__show__btn_item"
投票按钮_enabled组: "整数" = "ui_key:UI_STATE_GROUP__rect_btn_start__enabled__group"
投票按钮_disabled组: "整数" = "ui_key:UI_STATE_GROUP__rect_btn_start__disabled__group"
投票遮罩_show组: "整数" = "ui_key:UI_STATE_GROUP__vote_overlay__show__group"
投票取消提示_show组: "整数" = "ui_key:UI_STATE_GROUP__vote_cancel_tip__show__group"
结算提示_show组: "整数" = "ui_key:UI_STATE_GROUP__settle_tip__show__group"

# 关卡按钮映射（10 关完整保留，实际只开放第七关）
按钮到关卡号: "整数-整数字典" = {
    # 注意：关卡按钮为多状态组（unselected/selected/disabled），只有 unselected 状态下存在可点击按钮控件。
    "ui_key:关卡大厅-选关界面_html__rect_level_01__unselected__btn_item": 1,
    "ui_key:关卡大厅-选关界面_html__rect_level_02__unselected__btn_item": 2,
    "ui_key:关卡大厅-选关界面_html__rect_level_03__unselected__btn_item": 3,
    "ui_key:关卡大厅-选关界面_html__rect_level_04__unselected__btn_item": 4,
    "ui_key:关卡大厅-选关界面_html__rect_level_05__unselected__btn_item": 5,
    "ui_key:关卡大厅-选关界面_html__rect_level_06__unselected__btn_item": 6,
    "ui_key:关卡大厅-选关界面_html__rect_level_07__unselected__btn_item": 7,
    "ui_key:关卡大厅-选关界面_html__rect_level_08__unselected__btn_item": 8,
    "ui_key:关卡大厅-选关界面_html__rect_level_09__unselected__btn_item": 9,
    "ui_key:关卡大厅-选关界面_html__rect_level_10__unselected__btn_item": 10,
}
关卡号到未选组: "整数列表" = [
    "ui_key:UI_STATE_GROUP__rect_level_01__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_02__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_03__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_04__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_05__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_06__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_07__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_08__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_09__unselected__group",
    "ui_key:UI_STATE_GROUP__rect_level_10__unselected__group",
]
关卡号到已选组: "整数列表" = [
    "ui_key:UI_STATE_GROUP__rect_level_01__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_02__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_03__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_04__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_05__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_06__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_07__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_08__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_09__selected__group",
    "ui_key:UI_STATE_GROUP__rect_level_10__selected__group",
]
关卡号到禁用组: "整数列表" = [
    "ui_key:UI_STATE_GROUP__rect_level_01__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_02__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_03__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_04__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_05__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_06__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_07__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_08__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_09__disabled__group",
    "ui_key:UI_STATE_GROUP__rect_level_10__disabled__group",
]
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
    # ---------------------------- 交互控件索引（ui_key 占位符口径） ----------------------------
    GraphVariableConfig(
        name="进入倒计时秒数",
        variable_type="整数",
        default_value=3,
        description="投票达成后进入已投票关卡的倒计时秒数（UI选关_投票.countdown_sec）。注意：当前倒计时定时器序列与该值保持一致（默认 3 秒）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="关卡号到名称Key",
        variable_type="整数-字符串字典",
        default_value={
            1: "level_01_name",
            2: "level_02_name",
            3: "level_03_name",
            4: "level_04_name",
            5: "level_05_name",
            6: "level_06_name",
            7: "level_07_name",
            8: "level_08_name",
            9: "level_09_name",
            10: "level_10_name",
        },
        description="关卡号→UI选关_文本 中关卡名称字段 key（例如 level_07_name）。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    GraphVariableConfig(
        name="关卡号到作者Key",
        variable_type="整数-字符串字典",
        default_value={
            1: "level_01_author_name",
            2: "level_02_author_name",
            3: "level_03_author_name",
            4: "level_04_author_name",
            5: "level_05_author_name",
            6: "level_06_author_name",
            7: "level_07_author_name",
            8: "level_08_author_name",
            9: "level_09_author_name",
            10: "level_10_author_name",
        },
        description="关卡号→UI选关_文本 中作者名称字段 key（例如 level_07_author_name）。",
        is_exposed=False,
        dict_key_type="整数",
        dict_value_type="字符串",
    ),
    # ---------------------------- 选关预览（关卡展示元件） ----------------------------
    GraphVariableConfig(
        name="关卡号到展示元件ID_1",
        variable_type="元件ID列表",
        default_value=[
            "component_key:第一关展示元件",  # 1
            "component_key:第二关展示元件",  # 2
            "component_key:第三关展示元件",  # 3
            "component_key:第四关展示元件",  # 4
            "component_key:第五关展示元件",  # 5
            "component_key:第六关展示元件",  # 6
            "component_key:第七关展示元件",  # 7
            "component_key:第八关展示元件",  # 8
            "component_key:第九关展示元件",  # 9
            "component_key:第十关展示元件",  # 10
        ],
        description="预览展示元件（第 1 个）元件ID 查表（列表长度=10；序号=关卡号-1）。使用 component_key 占位符，导出/写回阶段从参考 .gil 回填真实元件ID。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="关卡号到展示元件ID_2",
        variable_type="元件ID列表",
        default_value=[
            0,  # 1
            0,  # 2
            0,  # 3
            0,  # 4
            0,  # 5
            0,  # 6
            0,  # 7
            0,  # 8
            0,  # 9
            0,  # 10
        ],
        description="预览展示元件（第 2 个）元件ID 查表（列表长度=10；序号=关卡号-1）。仅第 4/5/8 关使用，其余保持 0；使用 component_key 占位符，导出/写回阶段回填真实元件ID。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="关卡号到展示位置偏移",
        variable_type="三维向量列表",
        default_value=[
            (0.0, 0.11, 0.0),  # 1
            (0.0, 0.41, 0.0),  # 2
            (0.0, 0.0, 0.0),  # 3
            (-0.14, 0.28, -0.08),  # 4
            (-0.1, -0.28, -0.05),  # 5
            (0.0, -0.35, 0.0),  # 6
            (-0.09, 0.0, 0.0),  # 7
            (0.29,-0.29, 0.0),  # 8
            (-0.11, -0.18, 0.0),  # 9
            (0.0, -0.35, 0.0),  # 10
        ],
        description="预览元件相对“展示位置”的额外位置偏移查表（三维向量列表；长度=10；序号=关卡号-1）。用于修正预览元件摆放中心/高度等。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="关卡号到第二元件自带偏移",
        variable_type="三维向量列表",
        default_value=[
            (0.0, 0.0, 0.0),  # 1
            (0.0, 0.0, 0.0),  # 2
            (0.0, 0.0, 0.0),  # 3
            (0.0, 0.0, 0.0),  # 4
            (0.0, 0.0, 0.0),  # 5
            (0.0, 0.0, 0.0),  # 6
            (0.0, 0.0, 0.0),  # 7
            (0.0, 0.0, 0.0),  # 8
            (0.0, 0.0, 0.0),  # 9
            (0.0, 0.0, 0.0),  # 10
        ],
        description="双元件关卡（第 4/5/8 关）：第 2 个预览元件相对“展示基准位置（玩家当前位置 + (0,5,0)）”的偏移查表（三维向量列表；长度=10；序号=关卡号-1）。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="关卡号到展示旋转_1",
        variable_type="三维向量列表",
        default_value=[
            (0.0, 0.0, 0.0),  # 1
            (0.0, 0.0, 0.0),  # 2
            (0.0, 0.0, 0.0),  # 3
            (0.0, 90.0, 0.0),  # 4
            (0.0, 0.0, 0.0),  # 5
            (0.0, 0.0, 0.0),  # 6
            (0.0, 180.0, 0.0),  # 7
            (0.0, 0.0, 51.48),  # 8
            (0.0, -111.86, 0.0),  # 9
            (0.0, 0.0, 0.0),  # 10
        ],
        description="预览展示元件（第 1 个）旋转查表（三维向量列表；长度=10；序号=关卡号-1）。未配置关卡保持 (0,0,0)。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="关卡号到展示旋转_2",
        variable_type="三维向量列表",
        default_value=[
            (0.0, 0.0, 0.0),  # 1
            (0.0, 0.0, 0.0),  # 2
            (0.0, 0.0, 0.0),  # 3
            (0.0, 0.0, 0.0),  # 4
            (0.0, 0.0, 0.0),  # 5
            (0.0, 0.0, 0.0),  # 6
            (0.0, 0.0, 0.0),  # 7
            (0.0, 0.0, 0.0),  # 8
            (0.0, 0.0, 0.0),  # 9
            (0.0, 0.0, 0.0),  # 10
        ],
        description="预览展示元件（第 2 个）旋转查表（三维向量列表；长度=10；序号=关卡号-1）。未配置关卡保持 (0,0,0)。",
        is_exposed=False,
    ),
    # ---------------------------- 玩家出生站位（合并：玩家模板_关卡大厅_实体创建_传送到选关站位） ----------------------------
    GraphVariableConfig(
        name="玩家序号到玩家位置GUID",
        variable_type="整数-GUID字典",
        default_value={
            1: 1077952505,
            2: 1077952506,
            3: 1077952507,
            4: 1077952508,
        },
        description=(
            "玩家序号（1~4）→玩家站位实体 GUID（玩家实体创建时会被传送到对应站位）。"
            "默认值使用 entity_key:实体名 占位符，写回/导出阶段自动回填真实 GUID。"
        ),
        is_exposed=False,
        dict_key_type="整数 ",
        dict_value_type="GUID",
    ),
]

class 玩家模板_UI选关页_第七关_交互逻辑:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体: "实体", 事件源GUID: "GUID") -> None:
        自身玩家实体: "实体" = 获取自身实体(self.game)

        玩家GUID: "GUID" = 以实体查询GUID(self.game, 实体=自身玩家实体)
        玩家序号: "整数" = 根据玩家GUID获取玩家序号(self.game, 玩家GUID=玩家GUID)
        设置自定义变量(self.game, 目标实体=自身玩家实体, 变量名=玩家变量_玩家序号, 变量值=玩家序号, 是否触发事件=False)

        玩家位置GUID表: "整数-GUID字典" = 获取节点图变量(self.game, 变量名="玩家序号到玩家位置GUID")
        玩家位置GUID: "GUID" = 玩家位置GUID表[玩家序号]
        玩家位置实体: "实体" = 以GUID查询实体(self.game, GUID=玩家位置GUID)

        位置: "三维向量"
        旋转: "三维向量"
        位置, 旋转 = 获取实体位置与旋转(self.game, 目标实体=玩家位置实体)
        传送玩家(self.game, 玩家实体=自身玩家实体, 目标位置=位置, 目标旋转=旋转)
        return

    def on_关卡大厅_结算成功(self, 事件源实体: "实体", 事件源GUID: "GUID", 信号来源实体: "实体") -> None:
        自身玩家实体: "实体" = 获取自身实体(self.game)
        设置玩家结算成功状态(self.game, 玩家实体=自身玩家实体, 结算状态="胜利")
        return

    def on_界面控件组触发时(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        界面控件组组合索引: "整数",
        界面控件组索引: "整数",
    ) -> None:
        目标玩家: "实体" = 事件源实体
        组索引: "整数" = 界面控件组索引
        # 统一口径：本图直接用 UI 整数索引（1073741xxx 段）分发，仅使用「界面控件组索引」。
        # 若改为 `.ui_actions.json` 映射分发口径：应使用「事件源GUID」配合 `查询UI交互动作`。

        # 仅当玩家当前处于“选关页”布局时才处理（避免其它界面控件触发导致本图误写回/误推进）
        布局索引_选关页: "整数" = 获取节点图变量(self.game, 变量名="布局索引_选关页")
        if 布局索引_选关页 == 0:
            # 写回阶段未回填布局索引时：保持旧行为（不做布局过滤）
            pass
        else:
            当前布局索引: "整数" = 获取玩家当前界面布局(self.game, 玩家实体=目标玩家)
            if 当前布局索引 == 布局索引_选关页:
                pass
            else:
                return

        btn_exit: "整数" = 按钮索引_btn_exit
        btn_level_select: "整数" = 按钮索引_btn_level_select

        # 顶部退出 / 关卡选择：不做其它逻辑，只发送“前往选关”信号
        if (
            (组索引 == btn_exit)
            or (组索引 == btn_level_select)
        ):
            # 导航/切换音效：随机一个（30001/30002/30003）
            sfx_idx: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
            sfx_id: "整数" = (30001 + sfx_idx)
            玩家播放单次2D音效(
                self.game,
                目标实体=目标玩家,
                音效资产索引=sfx_id,
                音量=音量_满,
                播放速度=播放速度_默认,
            )
            发送信号(
                self.game,
                信号名="关卡大厅_前往选关",
            )
            return

        btn_settle: "整数" = 按钮索引_btn_settle
        btn_vote: "整数" = 按钮索引_rect_btn_start
        btn_vote_reject: "整数" = 按钮索引_btn_vote_reject

        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        倒计时进行中: "整数" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_进行中)
        倒计时模式: "字符串" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式)
        关卡列表: "整数列表" = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)

        # 预览图读取配置：由本图每次交互前同步到关卡实体自定义变量。
        预览_元件ID表1: "元件ID列表" = 获取节点图变量(self.game, 变量名="关卡号到展示元件ID_1")
        预览_元件ID表2: "元件ID列表" = 获取节点图变量(self.game, 变量名="关卡号到展示元件ID_2")
        预览_位置偏移表: "三维向量列表" = 获取节点图变量(self.game, 变量名="关卡号到展示位置偏移")
        预览_第二元件偏移表: "三维向量列表" = 获取节点图变量(self.game, 变量名="关卡号到第二元件自带偏移")
        预览_旋转表1: "三维向量列表" = 获取节点图变量(self.game, 变量名="关卡号到展示旋转_1")
        预览_旋转表2: "三维向量列表" = 获取节点图变量(self.game, 变量名="关卡号到展示旋转_2")
        设置自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示元件ID_1,
            变量值=预览_元件ID表1,
            是否触发事件=False,
        )
        设置自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示元件ID_2,
            变量值=预览_元件ID表2,
            是否触发事件=False,
        )
        设置自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示位置偏移,
            变量值=预览_位置偏移表,
            是否触发事件=False,
        )
        设置自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到第二元件自带偏移,
            变量值=预览_第二元件偏移表,
            是否触发事件=False,
        )
        设置自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示旋转_1,
            变量值=预览_旋转表1,
            是否触发事件=False,
        )
        设置自定义变量(
            self.game,
            目标实体=关卡实体,
            变量名=关卡实体自定义变量名_预览配置_关卡号到展示旋转_2,
            变量值=预览_旋转表2,
            是否触发事件=False,
        )

        # 顶部进行结算：需要投票通过才结算
        if 组索引 == btn_settle:
            # 倒计时锁：倒计时期间不允许重复发起/覆盖模式（避免倒计时被重置或 vote_mode 被劫持）
            if 倒计时进行中 == 1:
                tip_show: "整数" = 结算提示_show组
                text_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_文本")
                if 倒计时模式 == "settle":
                    text_map["settle_tip_status"] = "结算倒计时中"
                else:
                    text_map["settle_tip_status"] = "进入关卡倒计时中"
                修改界面布局内界面控件状态(self.game, 目标玩家, tip_show, "界面控件组状态_开启")
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示)
                启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示, 是否循环=False, 定时器序列=[2.5])
                return

            # 结算门槛：默认复用 UI 侧配置（required_cleared_count）；未达成则仅提示并返回
            list_map: "字符串_整数字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_列表")
            cleared_count: "整数" = list_map["cleared_count"]
            settle_cfg: "字符串_整数字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_结算提示")
            required_cleared: "整数" = settle_cfg["required_cleared_count"]
            if cleared_count >= required_cleared:
                pass
            else:
                text_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_文本")
                text_map["settle_tip_status"] = "未满足结算条件"
                tip_show: "整数" = 结算提示_show组
                修改界面布局内界面控件状态(self.game, 目标玩家, tip_show, "界面控件组状态_开启")
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示)
                启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示, 是否循环=False, 定时器序列=[2.5])
                return

            玩家播放单次2D音效(
                self.game,
                目标实体=目标玩家,
                音效资产索引=音效_允许,
                音量=音量_满,
                播放速度=播放速度_默认,
            )
            # 记录本玩家的“结算投票”（每人 0/1 票）
            设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_投票结算, 变量值=1, 是否触发事件=False)

            在线人数: "整数" = len(在场玩家列表)
            半数: "整数" = 除法运算(self.game, 左值=在线人数, 右值=2)
            门槛: "整数" = (半数 + 1)
            # 单人：不需要投票/遮罩倒计时，直接结算（避免“投票结果已达成”无意义弹窗）
            if 在线人数 <= 1:
                发送信号(self.game, 信号名=信号名_清空全员预览)
                for p in 在场玩家列表:
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票结算, 变量值=0, 是否触发事件=False)
                    设置玩家结算成功状态(self.game, 玩家实体=p, 结算状态="胜利")
                结算关卡(self.game)
                return

            已投票人数: "整数" = 0
            for p in 在场玩家列表:
                v: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票结算)
                if v == 1:
                    已投票人数 = (已投票人数 + 1)

            vote_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_投票")
            倒计时秒数: "整数" = 获取节点图变量(self.game, 变量名="进入倒计时秒数")
            在线人数文本: "字符串" = str(在线人数)
            已投票文本: "字符串" = str(已投票人数)
            门槛文本: "字符串" = str(门槛)
            倒计时文本: "字符串" = str(倒计时秒数)
            vote_map["total_players"] = 在线人数文本
            vote_map["voted_players"] = 已投票文本
            vote_map["majority_needed"] = 门槛文本
            vote_map["chosen_level_name"] = "进行结算"
            vote_map["countdown_label"] = "结算倒计时"
            vote_map["countdown_sec"] = 倒计时文本
            vote_map["vote_mode"] = "settle"
            # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量

            # 本玩家立即收到 toast：提示"已投票"
            text_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_文本")
            text_map["settle_tip_status"] = "已发起结算投票"

            tip_show: "整数" = 结算提示_show组
            修改界面布局内界面控件状态(self.game, 目标玩家, tip_show, "界面控件组状态_开启")
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示)
            启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示, 是否循环=False, 定时器序列=[2.5])

            # 过半：显示遮罩并启动倒计时，倒计时结束触发结算
            if 已投票人数 >= 门槛:
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_进行中, 变量值=1, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式, 变量值="settle", 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_目标关卡, 变量值=0, 是否触发事件=False)
                overlay_show: "整数" = 投票遮罩_show组
                vote_btn_enabled: "整数" = 投票按钮_enabled组
                vote_btn_disabled: "整数" = 投票按钮_disabled组
                for p in 在场玩家列表:
                    修改界面布局内界面控件状态(self.game, p, overlay_show, "界面控件组状态_开启")
                    # 遮罩显示期间：屏蔽底层关卡列表与底部投票按钮（避免点击穿透/快捷键遮挡“我拒绝”）
                    修改界面布局内界面控件状态(self.game, p, vote_btn_enabled, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, vote_btn_disabled, "界面控件组状态_开启")
                    for lv in 关卡列表:
                        未选组: "整数" = 关卡号到未选组[(lv - 1)]
                        已选组: "整数" = 关卡号到已选组[(lv - 1)]
                        禁用组: "整数" = 关卡号到禁用组[(lv - 1)]
                        修改界面布局内界面控件状态(self.game, p, 未选组, "界面控件组状态_关闭")
                        修改界面布局内界面控件状态(self.game, p, 已选组, "界面控件组状态_关闭")
                        修改界面布局内界面控件状态(self.game, p, 禁用组, "界面控件组状态_开启")

                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时)
                # 定时器序列需与“进入倒计时秒数”保持一致
                if 倒计时秒数 == 1:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0])
                elif 倒计时秒数 == 2:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0])
                elif 倒计时秒数 == 3:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0])
                elif 倒计时秒数 == 4:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0])
                elif 倒计时秒数 == 5:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0])
                elif 倒计时秒数 == 6:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
                elif 倒计时秒数 == 7:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
                elif 倒计时秒数 == 8:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
                elif 倒计时秒数 == 9:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
                elif 倒计时秒数 == 10:
                    启动定时器(
                        self.game,
                        目标实体=关卡实体,
                        定时器名称=定时器名_进入倒计时,
                        是否循环=False,
                        定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                    )
                else:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0])
            return

        # 关卡按钮：切换选中态
        点击索引: "整数" = 组索引
        命中关卡按钮: "布尔值" = (点击索引 in 按钮到关卡号)
        if 命中关卡按钮:
            # 遮罩/倒计时期间：底层关卡列表点击无效（双保险：即使引擎仍派发事件也不响应）
            if 倒计时进行中 == 1:
                return
            # 选中切换音效：随机一个（30001/30002/30003）
            sfx_idx: "整数" = 获取随机整数(self.game, 下限=0, 上限=2)
            sfx_id: "整数" = (30001 + sfx_idx)
            玩家播放单次2D音效(
                self.game,
                目标实体=目标玩家,
                音效资产索引=sfx_id,
                音量=音量_满,
                播放速度=播放速度_默认,
            )
            新关卡: "整数" = 按钮到关卡号[点击索引]
            旧关卡: "整数" = 获取自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_选中关卡)

            if 旧关卡 == 0:
                pass
            else:
                旧未选组: "整数" = 关卡号到未选组[(旧关卡 - 1)]
                旧已选组: "整数" = 关卡号到已选组[(旧关卡 - 1)]
                修改界面布局内界面控件状态(self.game, 目标玩家, 旧已选组, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, 目标玩家, 旧未选组, "界面控件组状态_开启")

            新未选组: "整数" = 关卡号到未选组[(新关卡 - 1)]
            新已选组: "整数" = 关卡号到已选组[(新关卡 - 1)]
            修改界面布局内界面控件状态(self.game, 目标玩家, 新未选组, "界面控件组状态_关闭")
            修改界面布局内界面控件状态(self.game, 目标玩家, 新已选组, "界面控件组状态_开启")

            设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_选中关卡, 变量值=新关卡, 是否触发事件=False)

            # 同步顶部标题（仅写两个会变化的 key）
            关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
            text_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_文本")
            名称Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="关卡号到名称Key")
            作者Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="关卡号到作者Key")
            名称Key: "字符串" = 名称Key表[新关卡]
            作者Key: "字符串" = 作者Key表[新关卡]
            名称: "字符串" = text_map[名称Key]
            作者: "字符串" = text_map[作者Key]
            text_map["level_name"] = 名称
            text_map["author_name"] = 作者

            vote_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_投票")
            vote_map["chosen_level_name"] = 名称
            # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量
            发送信号(self.game, 信号名=信号名_刷新预览, 目标玩家=目标玩家, 目标关卡=新关卡)
            return

        # 投票进入：按当前选中关卡发起投票，并进入倒计时遮罩
        if 组索引 == btn_vote:
            # 倒计时锁：倒计时期间不允许重复点击（避免重置倒计时或覆盖 vote_mode）
            if 倒计时进行中 == 1:
                return

            投票目标关卡: "整数" = 获取自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_选中关卡)

            # 未选择关卡：提示并返回（避免以 0 作为关卡号广播/写回）
            if 投票目标关卡 == 0:
                玩家播放单次2D音效(
                    self.game,
                    目标实体=目标玩家,
                    音效资产索引=音效_拒绝,
                    音量=音量_满,
                    播放速度=播放速度_默认,
                )
                text_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_文本")
                text_map["settle_tip_status"] = "请先选择关卡"
                tip_show: "整数" = 结算提示_show组
                修改界面布局内界面控件状态(self.game, 目标玩家, tip_show, "界面控件组状态_开启")
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示)
                启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_结算提示, 是否循环=False, 定时器序列=[2.5])
                return

            玩家播放单次2D音效(
                self.game,
                目标实体=目标玩家,
                音效资产索引=音效_允许,
                音量=音量_满,
                播放速度=播放速度_默认,
            )

            # 记录本玩家投票（每人仅一票）
            设置自定义变量(self.game, 目标实体=目标玩家, 变量名=玩家变量_投票关卡, 变量值=投票目标关卡, 是否触发事件=False)

            vote_btn_enabled: "整数" = 投票按钮_enabled组
            vote_btn_disabled: "整数" = 投票按钮_disabled组
            overlay_show: "整数" = 投票遮罩_show组

            关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
            发送信号(self.game, 信号名=信号名_刷新预览, 目标玩家=目标玩家, 目标关卡=投票目标关卡)
            # 进入投票即视为“锁定当前选中关卡”：同步顶部标题/作者与遮罩中的关卡名
            text_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_文本")
            名称Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="关卡号到名称Key")
            作者Key表: "整数-字符串字典" = 获取节点图变量(self.game, 变量名="关卡号到作者Key")
            名称Key: "字符串" = 名称Key表[投票目标关卡]
            作者Key: "字符串" = 作者Key表[投票目标关卡]
            名称: "字符串" = text_map[名称Key]
            作者: "字符串" = text_map[作者Key]
            text_map["level_name"] = 名称
            text_map["author_name"] = 作者
            vote_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_投票")
            vote_map["chosen_level_name"] = 名称

            在线人数: "整数" = len(在场玩家列表)
            半数: "整数" = 除法运算(self.game, 左值=在线人数, 右值=2)
            门槛: "整数" = (半数 + 1)
            # 单人：不需要投票/遮罩倒计时，直接进入关卡（避免“投票结果已达成”无意义弹窗）
            if 在线人数 <= 1:
                # 确认进入关卡：广播“开始关卡”信号（参数：第X关）
                发送信号(self.game, 信号名="关卡大厅_开始关卡", 第X关=投票目标关卡)
                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_进行中, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式, 变量值="无", 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_目标关卡, 变量值=0, 是否触发事件=False)
                发送信号(self.game, 信号名=信号名_清空全员预览)
                for p in 在场玩家列表:
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票关卡, 变量值=0, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票结算, 变量值=0, 是否触发事件=False)
                    # 仅第七关：选关页负责切换到第七关-游戏中布局；其它关卡由各自的开始关卡监听方处理 UI/传送等。
                    if 投票目标关卡 == 7:
                        布局索引_游戏中: "整数" = 获取节点图变量(self.game, 变量名="布局索引_第七关游戏中")
                        if 布局索引_游戏中 == 0:
                            return
                        切换当前界面布局(self.game, 目标玩家=p, 布局索引=布局索引_游戏中)
                return

            已投票人数: "整数" = 0
            for p in 在场玩家列表:
                v: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票关卡)
                if v == 投票目标关卡:
                    已投票人数 = (已投票人数 + 1)
                if v == 0:
                    修改界面布局内界面控件状态(self.game, p, vote_btn_disabled, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, vote_btn_enabled, "界面控件组状态_开启")
                else:
                    修改界面布局内界面控件状态(self.game, p, vote_btn_enabled, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, vote_btn_disabled, "界面控件组状态_开启")

            在线人数文本: "字符串" = str(在线人数)
            已投票文本: "字符串" = str(已投票人数)
            门槛文本: "字符串" = str(门槛)
            倒计时秒数: "整数" = 获取节点图变量(self.game, 变量名="进入倒计时秒数")
            倒计时文本: "字符串" = str(倒计时秒数)
            vote_map["total_players"] = 在线人数文本
            vote_map["voted_players"] = 已投票文本
            vote_map["majority_needed"] = 门槛文本
            vote_map["countdown_label"] = "进入关卡倒计时"
            vote_map["countdown_sec"] = 倒计时文本
            vote_map["vote_mode"] = "enter_level"
            # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量

            if 已投票人数 >= 门槛:
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_进行中, 变量值=1, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式, 变量值="enter_level", 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_目标关卡, 变量值=投票目标关卡, 是否触发事件=False)
                for p in 在场玩家列表:
                    修改界面布局内界面控件状态(self.game, p, overlay_show, "界面控件组状态_开启")
                    修改界面布局内界面控件状态(self.game, p, vote_btn_enabled, "界面控件组状态_关闭")
                    修改界面布局内界面控件状态(self.game, p, vote_btn_disabled, "界面控件组状态_开启")
                    # 遮罩显示期间：屏蔽底层关卡列表（避免点击穿透/快捷键遮挡“我拒绝”）
                    for lv in 关卡列表:
                        未选组: "整数" = 关卡号到未选组[(lv - 1)]
                        已选组: "整数" = 关卡号到已选组[(lv - 1)]
                        禁用组: "整数" = 关卡号到禁用组[(lv - 1)]
                        修改界面布局内界面控件状态(self.game, p, 未选组, "界面控件组状态_关闭")
                        修改界面布局内界面控件状态(self.game, p, 已选组, "界面控件组状态_关闭")
                        修改界面布局内界面控件状态(self.game, p, 禁用组, "界面控件组状态_开启")

                终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时)
                # 定时器序列需与“进入倒计时秒数”保持一致（序号会到达 N，从而让剩余=0）
                if 倒计时秒数 == 1:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0])
                elif 倒计时秒数 == 2:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0])
                elif 倒计时秒数 == 3:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0])
                elif 倒计时秒数 == 4:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0])
                elif 倒计时秒数 == 5:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0])
                elif 倒计时秒数 == 6:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
                elif 倒计时秒数 == 7:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
                elif 倒计时秒数 == 8:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
                elif 倒计时秒数 == 9:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
                elif 倒计时秒数 == 10:
                    启动定时器(
                        self.game,
                        目标实体=关卡实体,
                        定时器名称=定时器名_进入倒计时,
                        是否循环=False,
                        定时器序列=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                    )
                else:
                    启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时, 是否循环=False, 定时器序列=[1.0, 2.0, 3.0])
            return

        # 我拒绝：取消投票流程（隐藏遮罩 + 恢复按钮 + 弹提示）
        if 组索引 == btn_vote_reject:
            玩家播放单次2D音效(
                self.game,
                目标实体=目标玩家,
                音效资产索引=音效_拒绝,
                音量=音量_满,
                播放速度=播放速度_默认,
            )
            vote_btn_enabled: "整数" = 投票按钮_enabled组
            vote_btn_disabled: "整数" = 投票按钮_disabled组
            overlay_show: "整数" = 投票遮罩_show组
            cancel_show: "整数" = 投票取消提示_show组
            for p in 在场玩家列表:
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票关卡, 变量值=0, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_投票结算, 变量值=0, 是否触发事件=False)
                修改界面布局内界面控件状态(self.game, p, overlay_show, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, vote_btn_disabled, "界面控件组状态_关闭")
                修改界面布局内界面控件状态(self.game, p, vote_btn_enabled, "界面控件组状态_开启")
                修改界面布局内界面控件状态(self.game, p, cancel_show, "界面控件组状态_开启")
                # 恢复底层关卡按钮（避免遮罩关闭后仍残留 disabled）
                sel_level: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_选中关卡)
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

            关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_进入倒计时)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_进行中, 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_模式, 变量值="无", 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名=选关_投票倒计时_目标关卡, 变量值=0, 是否触发事件=False)
            vote_map: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI选关_投票")
            拒绝者昵称: "字符串" = 获取玩家昵称(self.game, 玩家实体=目标玩家)
            vote_map["vote_cancel_rejecter_name"] = 拒绝者昵称
            在线人数: "整数" = len(在场玩家列表)
            半数: "整数" = 除法运算(self.game, 左值=在线人数, 右值=2)
            门槛: "整数" = (半数 + 1)
            倒计时秒数: "整数" = 获取节点图变量(self.game, 变量名="进入倒计时秒数")
            在线人数文本: "字符串" = str(在线人数)
            门槛文本: "字符串" = str(门槛)
            倒计时文本: "字符串" = str(倒计时秒数)
            vote_map["total_players"] = 在线人数文本
            vote_map["voted_players"] = "0"
            vote_map["majority_needed"] = 门槛文本
            vote_map["countdown_label"] = "进入关卡倒计时"
            vote_map["countdown_sec"] = 倒计时文本
            vote_map["vote_mode"] = "enter_level"
            # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量

            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_投票取消提示)
            启动定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_投票取消提示, 是否循环=False, 定时器序列=[2.0])
            return

        return

    def register_handlers(self):
        self.game.register_event_handler(
            "实体创建时",
            self.on_实体创建时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "关卡大厅_结算成功",
            self.on_关卡大厅_结算成功,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "界面控件组触发时",
            self.on_界面控件组触发时,
            owner=self.owner_entity,
        )
        # 说明：本图仅保留 UI 点击入口；倒计时/提示定时器已下沉到关卡实体图（关卡实体_UI选关页_第七关_倒计时执行）。

if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

