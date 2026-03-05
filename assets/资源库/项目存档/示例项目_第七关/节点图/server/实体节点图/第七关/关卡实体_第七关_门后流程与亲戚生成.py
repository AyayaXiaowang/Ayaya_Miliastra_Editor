"""
graph_id: server_test_project_level7_postdoor_relative_spawn
graph_name: 关卡实体_第七关_门后流程与亲戚生成
graph_type: server
description: 第七关关卡级流程拆分图（挂载关卡实体）：

- 监听 `第七关_门_关闭完成`：
  - 执行“关门完成后业务待办”（进入结算 / 请求下一位亲戚）。
- 监听 `第七关_下发亲戚数据`：
  - 按外观查表创建亲戚组件实体；
  - 发送门动作信号 `第七关_门_动作(打开)`。
- 监听 `第七关_结算派发(允许票, 拒绝票)`：
  - 读取本回合真相与玩家选择，完成得分与资源扣减；
  - 写回 `UI战斗_揭晓`、`UI战斗_文本`，并同步玩家 HUD/结算展示用的玩家变量（`ui_battle_*`）；
  - 展示揭晓遮罩并启动结果态停留计时器（由公共控制图在计时结束后派发回合推进）。

说明：
- 本图挂载在关卡实体（GUID=1094713345）。
- 亲戚生成与结算切页配置由本图自身 GRAPH_VARIABLES 提供（作用域局部，不跨图读取）。
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

玩家变量_回合选择: "字符串" = "ui_battle_choice"
玩家变量_压岁钱: "字符串" = "ui_battle_money"
玩家变量_积分: "字符串" = "ui_battle_score"
玩家变量_排名: "字符串" = "ui_battle_rank"
玩家变量_压岁钱变化: "字符串" = "ui_battle_moneyd"
玩家变量_积分变化: "字符串" = "ui_battle_scored"
玩家变量_完整度: "字符串" = "ui_battle_integrity"
玩家变量_手办存活: "字符串" = "ui_battle_survival"
玩家变量_完整度变化: "字符串" = "ui_battle_integrityd"
玩家变量_手办存活变化: "字符串" = "ui_battle_survivald"

# 结算页左栏：状态与评语（每玩家独立，绑定到 ps.* 文本变量）
玩家变量_结算_完整度状态: "字符串" = "ui_settle_i_st"
玩家变量_结算_手办状态: "字符串" = "ui_settle_s_st"
玩家变量_结算_评语1: "字符串" = "ui_settle_ev1"
玩家变量_结算_评语2: "字符串" = "ui_settle_ev2"
定时器名_结算停留: "字符串" = "ui_battle_settlement_hold"
关卡变量_本回合真相为允许: "字符串" = "第七关_本回合_真相为允许"
关卡变量_本回合是否小孩: "字符串" = "第七关_本回合_是否小孩"

关卡变量_门关闭完成后待办: "字符串" = "第七关_门_关闭完成后待办"
信号名_门动作: "字符串" = "第七关_门_动作"
信号名_门关闭完成: "字符串" = "第七关_门_关闭完成"
定时器名_结算页自动返回: "字符串" = "ui_level7_result_auto_return"
定时器名_关门兜底: "字符串" = "ui_level7_door_close_fallback"

音量_满: "整数" = 100
播放速度_默认: "浮点数" = 1.0
BGM_结算阶段: "整数" = 10102
音效_破坏: "整数" = 50013

# UI 状态组占位符：按“整数端口”写回时会在导出阶段解析为真实组索引，不会按字符串落库。
揭晓遮罩_result组: "整数" = "ui_key:UI_STATE_GROUP__battle_settlement_overlay__result__group"

GRAPH_VARIABLES: list[GraphVariableConfig] = [
    # ---------------------------- 投票结算（对外暴露） ----------------------------
    GraphVariableConfig(
        name="结算_完整度_每次错误扣除",
        variable_type="整数",
        default_value=5,
        description="每次投错扣除的完整度。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="结算_手办_每次放错扣除",
        variable_type="整数",
        default_value=1,
        description="应拒绝但被放入时，每次扣除的手办数。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="积分_权重_完整度",
        variable_type="整数",
        default_value=10,
        description="积分扣分权重：每损失 1 点『年夜饭完整度』扣除的积分。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="积分_权重_手办",
        variable_type="整数",
        default_value=50,
        description="积分扣分权重：每损失 1 个『手办存活』扣除的积分。",
        is_exposed=True,
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
    GraphVariableConfig(
        name="布局索引_结算页",
        variable_type="整数",
        default_value=0,
        description="UI布局索引：第七关结算页（第七关-结算.html）。默认 0；写回阶段会尝试自动回填。",
        is_exposed=False,
    ),
    GraphVariableConfig(
        name="结算页自动返回秒数",
        variable_type="整数",
        default_value=0,
        description="结算页自动返回选关页的等待秒数。>0 表示启用自动返回；=0 表示不自动返回（最后总结算停留在结算页）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="关门兜底秒数",
        variable_type="整数",
        default_value=6,
        description="关门完成信号兜底：发送『第七关_门_动作(关闭)』后若 N 秒仍未收到『第七关_门_关闭完成』，则由关卡实体补发完成信号，避免流程卡死。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="游戏场地GUID",
        variable_type="GUID",
        default_value="entity_key:第七关-场景",
        description="对外暴露：第七关场地（出生/展示锚点）实体 GUID。使用 entity_key 占位符，写回阶段从参考 .gil 回填真实 GUID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="亲戚生成相对偏移",
        variable_type="三维向量",
        default_value=(0.0, 1.94, 0.12),
        description="对外暴露：亲戚生成点相对场地实体的位置偏移（x,y,z）。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="外观索引_身体",
        variable_type="字符串-整数字典",
        default_value={"瘦马": 0, "肥马": 1, "老马": 2, "小孩马": 3, "正常马": 4},
        description="内部：body 类型文本→索引（用于查表）。",
        is_exposed=False,
        dict_key_type="字符串",
        dict_value_type="整数",
    ),
    GraphVariableConfig(
        name="外观元件表_身体",
        variable_type="元件ID列表",
        default_value=[
            "component_key:像素画 瘦马",  # 瘦马
            "component_key:像素画 矮胖成年男",  # 肥马
            "component_key:像素画 老马",  # 老马
            "component_key:像素画 小马",  # 小孩马
            "component_key:像素画 高瘦成年男",  # 正常马
        ],
        description="对外暴露：身体元件查表（索引顺序：瘦马/肥马/老马/小孩马/正常马）。使用 component_key 占位符，导出/写回阶段从参考 .gil 回填真实元件ID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="外观索引_头发",
        variable_type="字符串-整数字典",
        default_value={"大背头": 0, "好看头": 1, "飞机头": 2, "马尾": 3, "普通头发": 4, "帽子": 5},
        description="内部：hair 类型文本→索引（用于查表）。",
        is_exposed=False,
        dict_key_type="字符串",
        dict_value_type="整数",
    ),
    GraphVariableConfig(
        name="外观元件表_头发",
        variable_type="元件ID列表",
        default_value=[
            "component_key:大背头",
            "component_key:好看的头发",
            "component_key:飞机头",
            "component_key:马尾",
            "component_key:普通头发",
            "component_key:帽子",
        ],
        description="对外暴露：头发元件查表（索引顺序：大背头/好看头/飞机头/马尾/普通头发/帽子）。使用 component_key 占位符，导出/写回阶段回填真实元件ID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="外观索引_胡子",
        variable_type="字符串-整数字典",
        default_value={"无": 0, "小胡茬": 1, "长胡子": 2},
        description="内部：beard 类型文本→索引（用于查表）。",
        is_exposed=False,
        dict_key_type="字符串",
        dict_value_type="整数",
    ),
    GraphVariableConfig(
        name="外观元件表_胡子",
        variable_type="元件ID列表",
        default_value=[
            0,  # 无
            "component_key:小胡茬",
            "component_key:长胡子",
        ],
        description="对外暴露：胡子元件查表（索引顺序：无/小胡茬/长胡子；0 表示不生成该元件）。使用 component_key 占位符，导出/写回阶段回填真实元件ID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="外观索引_眼镜",
        variable_type="字符串-整数字典",
        default_value={"无": 0, "普通眼镜": 1, "墨镜": 2},
        description="内部：glasses 类型文本→索引（用于查表）。",
        is_exposed=False,
        dict_key_type="字符串",
        dict_value_type="整数",
    ),
    GraphVariableConfig(
        name="外观元件表_眼镜",
        variable_type="元件ID列表",
        default_value=[
            0,  # 无
            "component_key:普通眼镜",
            "component_key:墨镜",
        ],
        description="对外暴露：眼镜元件查表（索引顺序：无/普通眼镜/墨镜；0 表示不生成该元件）。使用 component_key 占位符，导出/写回阶段回填真实元件ID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="外观索引_衣服",
        variable_type="字符串-整数字典",
        default_value={"无": 0, "西装": 1, "棉袄": 2, "卫衣": 3, "夏装": 4, "东北大棉袄": 5},
        description="内部：clothes 类型文本→索引（用于查表）。",
        is_exposed=False,
        dict_key_type="字符串",
        dict_value_type="整数",
    ),
    GraphVariableConfig(
        name="外观元件表_衣服",
        variable_type="元件ID列表",
        default_value=[
            0,  # 无
            "component_key:西装",
            "component_key:棉袄",
            "component_key:卫衣",
            "component_key:夏装",
            "component_key:东北大棉袄",
        ],
        description="对外暴露：衣服元件查表（索引顺序：无/西装/棉袄/卫衣/夏装/东北大棉袄；0 表示不生成该元件）。使用 component_key 占位符，导出/写回阶段回填真实元件ID。",
        is_exposed=True,
    ),
    GraphVariableConfig(
        name="外观索引_领饰",
        variable_type="字符串-整数字典",
        default_value={"无": 0, "铃铛": 1, "领带": 2, "花纹围巾": 3, "红围巾": 4},
        description="内部：neckwear 类型文本→索引（用于查表）。",
        is_exposed=False,
        dict_key_type="字符串",
        dict_value_type="整数",
    ),
    GraphVariableConfig(
        name="外观元件表_领饰",
        variable_type="元件ID列表",
        default_value=[
            0,  # 无
            "component_key:铃铛",
            "component_key:领带",
            "component_key:花纹围巾",
            "component_key:红围巾",
        ],
        description="对外暴露：领饰元件查表（索引顺序：无/铃铛/领带/花纹围巾/红围巾；0 表示不生成该元件）。使用 component_key 占位符，导出/写回阶段回填真实元件ID。",
        is_exposed=True,
    ),
]


class 关卡实体_第七关_门后流程与亲戚生成:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    # ---------------------------- 关门完成兜底（避免门事件缺失导致流程卡死） ----------------------------
    def on_第七关_门_动作(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        目标状态: "字符串",
    ) -> None:
        """监听门动作：当收到『关闭』时启动兜底定时器；收到『打开』时取消兜底定时器。"""
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        if 目标状态 == "关闭":
            兜底秒数: "整数" = 获取节点图变量(self.game, 变量名="关门兜底秒数")
            兜底秒数_浮点: "浮点数" = 数据类型转换(self.game, 输入=兜底秒数)
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_关门兜底)
            启动定时器(
                self.game,
                目标实体=关卡实体,
                定时器名称=定时器名_关门兜底,
                是否循环=False,
                定时器序列=[兜底秒数_浮点],
            )
        else:
            # 打开：不需要“关门完成”兜底
            终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_关门兜底)
        return

    def on_定时器触发时(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        定时器名称: "字符串",
        定时器序列序号: "整数",
        循环次数: "整数",
    ) -> None:
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        if 定时器名称 == 定时器名_关门兜底:
            待办: "字符串" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办)
            if 待办 == "无":
                return
            # 兜底：补发“关门完成”，由本图统一走待办分发逻辑（若真门后续再发信号，会被待办锁去重）。
            发送信号(self.game, 信号名=信号名_门关闭完成)
        return

    def on_第七关_结算派发(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
        允许票: "整数",
        拒绝票: "整数",
    ) -> None:
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
        # 变化值不要用“新分-旧分”的两次读取相减：在拉取式执行语义下，两次读取可能在同一时刻发生，
        # 节点图层面表现为“同源相减(X-X=0)”。直接按本回合结算规则计算 delta 更稳定。
        加分: "整数" = 100
        扣分: "整数" = -50

        真相为允许: "布尔值" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合真相为允许)
        投票结果为允许: "布尔值" = 允许票 > 拒绝票
        判断正确: "布尔值" = 投票结果为允许 == 真相为允许

        reveal_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_揭晓")
        reveal_text["徽章_结果"] = "结果"
        reveal_text["按钮_关闭"] = "继续"
        if 判断正确:
            reveal_text["结果_判定"] = "判断正确"
        else:
            reveal_text["结果_判定"] = "判断错误"

        if 真相为允许:
            reveal_text["结果_真相"] = "真亲戚"
            reveal_text["结果_描述"] = "这位亲戚是真的。"
        else:
            reveal_text["结果_真相"] = "年兽伪装"
            reveal_text["结果_描述"] = "这位“亲戚”其实是年兽伪装。"

        # 压岁钱：投对 +100，否则 -50（个人压岁钱与变化值均写回玩家变量）
        for p in 在场玩家列表:
            c: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择)
            当前钱: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱)
            if 真相为允许:
                if c == 1:
                    delta: "整数" = 加分
                    新钱: "整数" = (当前钱 + 100)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱, 变量值=新钱, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱变化, 变量值=delta, 是否触发事件=False)
                else:
                    delta: "整数" = 扣分
                    新钱: "整数" = (当前钱 - 50)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱, 变量值=新钱, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱变化, 变量值=delta, 是否触发事件=False)
            else:
                if c == 2:
                    delta: "整数" = 加分
                    新钱: "整数" = (当前钱 + 100)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱, 变量值=新钱, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱变化, 变量值=delta, 是否触发事件=False)
                else:
                    delta: "整数" = 扣分
                    新钱: "整数" = (当前钱 - 50)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱, 变量值=新钱, 是否触发事件=False)
                    设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_压岁钱变化, 变量值=delta, 是否触发事件=False)

        每次错误扣: "整数" = 获取节点图变量(self.game, 变量名="结算_完整度_每次错误扣除")
        每次放错扣: "整数" = 获取节点图变量(self.game, 变量名="结算_手办_每次放错扣除")
        积分权重_完整度: "整数" = 获取节点图变量(self.game, 变量名="积分_权重_完整度")
        积分权重_手办: "整数" = 获取节点图变量(self.game, 变量名="积分_权重_手办")

        # 玩家资源（个人）：按个人选择扣完整度/扣手办，并写回变化值（用于揭晓面板）
        if 真相为允许:
            本回合是否小孩: "布尔值" = False
        else:
            本回合是否小孩: "布尔值" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_本回合是否小孩)

        for p in 在场玩家列表:
            c: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_回合选择)

            # 判定个人是否投对（口径与计分一致）
            if 真相为允许:
                玩家投对: "布尔值" = c == 1
            else:
                玩家投对: "布尔值" = c == 2

            扣完整度_个人: "整数" = 0
            if 玩家投对:
                pass
            else:
                扣完整度_个人 = 每次错误扣

            扣手办_个人: "整数" = 0
            if 真相为允许:
                pass
            else:
                if 本回合是否小孩 and 投票结果为允许 and (c == 1):
                    扣手办_个人 = 每次放错扣
                else:
                    pass

            旧完整度_p: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度)
            旧手办_p: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活)
            新完整度_p: "整数" = (旧完整度_p - 扣完整度_个人)
            新手办_p: "整数" = (旧手办_p - 扣手办_个人)

            # 防御：完整度/手办不允许为负数，否则 UI 进度条可能异常
            新完整度_safe: "整数" = max(0, 新完整度_p)
            新手办_safe: "整数" = max(0, 新手办_p)

            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度, 变量值=新完整度_safe, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活, 变量值=新手办_safe, 是否触发事件=False)

            完整度变化值_p: "整数" = (0 - 扣完整度_个人)
            手办变化值_p: "整数" = (0 - 扣手办_个人)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度变化, 变量值=完整度变化值_p, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活变化, 变量值=手办变化值_p, 是否触发事件=False)

            # 积分：按规则拆分（积分 = 压岁钱 - 年夜饭损失*权重 - 手办损失*权重），采用增量维护避免“写回后再读”不生效。
            旧积分_p: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
            if 玩家投对:
                压岁钱变化_p: "整数" = 加分
            else:
                压岁钱变化_p: "整数" = 扣分
            实际扣完整度_p: "整数" = (旧完整度_p - 新完整度_safe)
            实际扣手办_p: "整数" = (旧手办_p - 新手办_safe)
            完整度扣分_p: "整数" = (积分权重_完整度 * 实际扣完整度_p)
            手办扣分_p: "整数" = (积分权重_手办 * 实际扣手办_p)
            积分变化_1_p: "整数" = (压岁钱变化_p - 完整度扣分_p)
            积分变化_p: "整数" = (积分变化_1_p - 手办扣分_p)
            新积分_p: "整数" = (旧积分_p + 积分变化_p)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分, 变量值=新积分_p, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分变化, 变量值=积分变化_p, 是否触发事件=False)

            if (扣完整度_个人 > 0) or (扣手办_个人 > 0):
                玩家播放单次2D音效(
                    self.game,
                    目标实体=p,
                    音效资产索引=音效_破坏,
                    音量=音量_满,
                    播放速度=播放速度_默认,
                )

        # 揭晓面板：标题与标签保持关卡字典（变化值由玩家变量写回）
        reveal_text["变化_压岁钱_标题"] = "压岁钱"
        reveal_text["变化_压岁钱"] = " "
        reveal_text["变化_得分_标题"] = "积分"
        reveal_text["变化_得分"] = " "
        reveal_text["变化_完整度_标题"] = "年夜饭完整度"
        reveal_text["变化_完整度"] = " "
        reveal_text["变化_存活_标题"] = "手办存活"
        reveal_text["变化_存活"] = " "

        battle_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_文本")

        # 刷新审判庭：按积分排名展示（同分按在场顺序稳定）
        player_count: "整数" = len(在场玩家列表)

        # slot -> key 映射：避免在图逻辑中做字符串拼接
        slot_to_name_key: "整数-字符串字典" = {1: "审判1名", 2: "审判2名", 3: "审判3名", 4: "审判4名"}
        slot_to_pts_key: "整数-字符串字典" = {1: "审判1分", 2: "审判2分", 3: "审判3分", 4: "审判4分"}
        slot_to_state_key: "整数-字符串字典" = {1: "审判1态", 2: "审判2态", 3: "审判3态", 4: "审判4态"}

        # 状态颜色：与 UI战斗_文本.审判N态 同步（用于 <color={1:lv.UI战斗_颜色.审判N态}>）
        style_colors: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI样式_颜色")
        c_thinking: "字符串" = style_colors["状态_思考中"]
        c_allow: "字符串" = style_colors["状态_允许"]
        c_reject: "字符串" = style_colors["状态_拒绝"]
        battle_color: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI战斗_颜色")

        # 积分排序：用于“按排名显示”
        p0: "实体" = 在场玩家列表[0]
        p0_score: "整数" = 获取自定义变量(self.game, 目标实体=p0, 变量名=玩家变量_积分)
        score_dict: "实体-整数字典" = {p0: p0_score}
        for p in 在场玩家列表:
            score: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
            score_dict[p] = score

        sorted_players, sorted_scores = 对字典按值排序(self.game, 字典=score_dict, 排序方式="排序规则_逆序")

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
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_排名, 变量值=slot, 是否触发事件=False)
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
                battle_text[state_key] = " "
                battle_color[state_key] = c_thinking

        for p in 在场玩家列表:
            修改界面布局内界面控件状态(self.game, p, 揭晓遮罩_result组, "界面控件组状态_开启")
        # 结算停留定时器由公共控制图统一启动，并在到点时派发回合推进（避免跨图定时器回调语义差异导致不自动推进）
        return

    def on_第七关_门_关闭完成(
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

        # 收到真实“关门完成”时立即取消兜底定时器（兜底信号自身也会走到这里，幂等）。
        终止定时器(self.game, 目标实体=关卡实体, 定时器名称=定时器名_关门兜底)

        在场玩家列表: "实体列表" = 获取在场玩家实体列表(self.game)
        待办: "字符串" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办)
        if 待办 == "无":
            return
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名=关卡变量_门关闭完成后待办, 变量值="无", 是否触发事件=False)

        # 进入结算：关门完成后切换结算页并切 BGM
        if 待办 == "进入结算":
            # 清理亲戚实体（门关闭后再销毁，避免穿帮）
            旧身体实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_身体实体")
            旧眼睛实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_眼睛实体")
            旧头发实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_头发实体")
            旧胡子实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_胡子实体")
            旧领带实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_领带实体")
            旧衣服实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_衣服实体")
            销毁实体(self.game, 目标实体=旧眼睛实体)
            销毁实体(self.game, 目标实体=旧头发实体)
            销毁实体(self.game, 目标实体=旧胡子实体)
            销毁实体(self.game, 目标实体=旧领带实体)
            销毁实体(self.game, 目标实体=旧衣服实体)
            销毁实体(self.game, 目标实体=旧身体实体)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_身体实体", 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_眼睛实体", 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_头发实体", 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_胡子实体", 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_领带实体", 变量值=0, 是否触发事件=False)
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_衣服实体", 变量值=0, 是否触发事件=False)

            # 结算页榜单：按积分降序写回 UI结算_文本（供 第七关-结算.html 绑定）
            result_text: "字符串_字符串字典" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="UI结算_文本")

            player_count: "整数" = 获取列表长度(self.game, 列表=在场玩家列表)
            p0: "实体" = 获取列表对应值(self.game, 列表=在场玩家列表, 序号=0)
            p0_pts: "整数" = 获取自定义变量(self.game, 目标实体=p0, 变量名=玩家变量_积分)
            score_dict: "实体-整数字典" = {p0: p0_pts}
            for p in 在场玩家列表:
                pts: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_积分)
                对字典设置或新增键值对(self.game, 字典=score_dict, 键=p, 值=pts)
            sorted_players, sorted_scores = 对字典按值排序(self.game, 字典=score_dict, 排序方式="排序规则_逆序")

            # slot1（至少 1 人）
            top1_p: "实体" = 获取列表对应值(self.game, 列表=sorted_players, 序号=0)
            top1_pts: "整数" = 获取列表对应值(self.game, 列表=sorted_scores, 序号=0)
            top1_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top1_p)
            top1_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top1_p, 变量名=玩家变量_压岁钱)
            top1_money: "字符串" = str(top1_money_raw)
            top1_score: "字符串" = str(top1_pts)
            对字典设置或新增键值对(self.game, 字典=result_text, 键="榜1名次", 值="1")
            对字典设置或新增键值对(self.game, 字典=result_text, 键="榜1名", 值=top1_name)
            对字典设置或新增键值对(self.game, 字典=result_text, 键="榜1标签", 值=" ")
            对字典设置或新增键值对(self.game, 字典=result_text, 键="榜1钱前缀", 值="¥ ")
            对字典设置或新增键值对(self.game, 字典=result_text, 键="榜1钱", 值=top1_money)
            对字典设置或新增键值对(self.game, 字典=result_text, 键="榜1分", 值=top1_score)
            对字典设置或新增键值对(self.game, 字典=result_text, 键="榜1分后缀", 值=" 积分")

            # slot2
            if player_count >= 2:
                top2_p: "实体" = 获取列表对应值(self.game, 列表=sorted_players, 序号=1)
                top2_pts: "整数" = 获取列表对应值(self.game, 列表=sorted_scores, 序号=1)
                top2_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top2_p)
                top2_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top2_p, 变量名=玩家变量_压岁钱)
                top2_money: "字符串" = str(top2_money_raw)
                top2_score: "字符串" = str(top2_pts)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2名次", 值="2")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2名", 值=top2_name)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2标签", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2钱前缀", 值="¥ ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2钱", 值=top2_money)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2分", 值=top2_score)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2分后缀", 值=" 积分")
            else:
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2名次", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2名", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2标签", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2钱前缀", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2钱", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2分", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜2分后缀", 值=" ")

            # slot3
            if player_count >= 3:
                top3_p: "实体" = 获取列表对应值(self.game, 列表=sorted_players, 序号=2)
                top3_pts: "整数" = 获取列表对应值(self.game, 列表=sorted_scores, 序号=2)
                top3_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top3_p)
                top3_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top3_p, 变量名=玩家变量_压岁钱)
                top3_money: "字符串" = str(top3_money_raw)
                top3_score: "字符串" = str(top3_pts)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3名次", 值="3")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3名", 值=top3_name)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3标签", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3钱前缀", 值="¥ ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3钱", 值=top3_money)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3分", 值=top3_score)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3分后缀", 值=" 积分")
            else:
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3名次", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3名", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3标签", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3钱前缀", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3钱", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3分", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜3分后缀", 值=" ")

            # slot4
            if player_count >= 4:
                top4_p: "实体" = 获取列表对应值(self.game, 列表=sorted_players, 序号=3)
                top4_pts: "整数" = 获取列表对应值(self.game, 列表=sorted_scores, 序号=3)
                top4_name: "字符串" = 获取玩家昵称(self.game, 玩家实体=top4_p)
                top4_money_raw: "整数" = 获取自定义变量(self.game, 目标实体=top4_p, 变量名=玩家变量_压岁钱)
                top4_money: "字符串" = str(top4_money_raw)
                top4_score: "字符串" = str(top4_pts)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4名次", 值="4")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4名", 值=top4_name)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4标签", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4钱前缀", 值="¥ ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4钱", 值=top4_money)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4分", 值=top4_score)
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4分后缀", 值=" 积分")
            else:
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4名次", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4名", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4标签", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4钱前缀", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4钱", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4分", 值=" ")
                对字典设置或新增键值对(self.game, 字典=result_text, 键="榜4分后缀", 值=" ")
            # 自定义变量的 dict/list 为引用式：原地修改后无需再次设置自定义变量

            布局索引_结算页: "整数" = 获取节点图变量(self.game, 变量名="布局索引_结算页")
            if 布局索引_结算页 == 0:
                return
            自动返回秒数: "整数" = 获取节点图变量(self.game, 变量名="结算页自动返回秒数")
            for p in 在场玩家列表:
                # 结算页左栏评语/状态：按个人完整度/手办存活分段写回（避免使用 lv.UI结算_文本 的全局键导致多人串值）
                integrity: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_完整度)
                survival: "整数" = 获取自定义变量(self.game, 目标实体=p, 变量名=玩家变量_手办存活)

                integrity_status: "字符串" = " "
                if integrity >= 80:
                    integrity_status: "字符串" = "状态良好"
                elif integrity >= 60:
                    integrity_status: "字符串" = "轻微受损"
                elif integrity >= 40:
                    integrity_status: "字符串" = "明显受损"
                elif integrity >= 20:
                    integrity_status: "字符串" = "严重受损"
                else:
                    integrity_status: "字符串" = "惨不忍睹"

                survival_status: "字符串" = " "
                if survival >= 8:
                    survival_status: "字符串" = "基本完好"
                elif survival >= 5:
                    survival_status: "字符串" = "有些损失"
                elif survival >= 2:
                    survival_status: "字符串" = "损失惨重"
                elif survival >= 1:
                    survival_status: "字符串" = "濒临团灭"
                else:
                    survival_status: "字符串" = "全军覆没"

                ev1: "字符串" = " "
                ev2: "字符串" = " "
                if (integrity >= 80) and (survival >= 8):
                    ev1: "字符串" = "年夜饭保住了，真棒！"
                    ev2: "字符串" = "妈妈：不错，今年给你个大大的红包。"
                elif (integrity >= 60) and (survival >= 5):
                    ev1: "字符串" = "总体还行：小磕小碰，但家底没被掏空。"
                    ev2: "字符串" = "妈妈：下次别让熊孩子摸到手办。"
                elif (integrity >= 40) and (survival >= 3):
                    ev1: "字符串" = "损失不小：年夜饭损失过半。"
                    ev2: "字符串" = "妈妈已在路上，建议你先把门栓上。"
                elif (integrity >= 20) and (survival >= 1):
                    ev1: "字符串" = "情况危急：年夜饭消耗殆尽，好在还剩一个鸡腿。"
                    ev2: "字符串" = "妈正拿着鸡毛掸子赶来，预计到达时间：10 秒。"
                else:
                    ev1: "字符串" = "这年过得太惨了，菜被偷吃光，晚饭该何去何从。"
                    ev2: "字符串" = "妈正拿着鸡毛掸子赶来，预计到达时间：10 秒。"

                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_结算_完整度状态, 变量值=integrity_status, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_结算_手办状态, 变量值=survival_status, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_结算_评语1, 变量值=ev1, 是否触发事件=False)
                设置自定义变量(self.game, 目标实体=p, 变量名=玩家变量_结算_评语2, 变量值=ev2, 是否触发事件=False)

                修改玩家背景音乐(
                    self.game,
                    目标实体=p,
                    背景音乐索引=BGM_结算阶段,
                    开始时间=0.0,
                    结束时间=9999.0,
                    音量=音量_满,
                    是否循环播放=True,
                    循环播放间隔=0.0,
                    播放速度=播放速度_默认,
                    是否允许渐入渐出=True,
                )
                设置玩家结算成功状态(self.game, 玩家实体=p, 结算状态="胜利")
                切换当前界面布局(self.game, 目标玩家=p, 布局索引=布局索引_结算页)
                # 结算页定时器：
                # - 序号=1：进入结算页后首次刷新榜单（无需玩家点击）
                # - 序号=自动返回秒数：到点自动返回选关（仅当 `结算页自动返回秒数>0`；定时器序列序号=序列元素值）
                终止定时器(self.game, 目标实体=p, 定时器名称=定时器名_结算页自动返回)
                首次刷新秒数: "浮点数" = 数据类型转换(self.game, 输入=1)
                if 自动返回秒数 > 0:
                    自动返回秒数_浮点: "浮点数" = 数据类型转换(self.game, 输入=自动返回秒数)
                    启动定时器(
                        self.game,
                        目标实体=p,
                        定时器名称=定时器名_结算页自动返回,
                        是否循环=False,
                        定时器序列=[首次刷新秒数, 自动返回秒数_浮点],
                    )
                else:
                    # 最后总结算：只做首次刷新，不自动跳回选关
                    启动定时器(
                        self.game,
                        目标实体=p,
                        定时器名称=定时器名_结算页自动返回,
                        是否循环=False,
                        定时器序列=[首次刷新秒数],
                    )
            return

        # 开局/下一回合：门关闭后替换并生成亲戚 → 开门进场
        旧身体实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_身体实体")
        旧眼睛实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_眼睛实体")
        旧头发实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_头发实体")
        旧胡子实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_胡子实体")
        旧领带实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_领带实体")
        旧衣服实体: "实体" = 获取自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_衣服实体")
        销毁实体(self.game, 目标实体=旧眼睛实体)
        销毁实体(self.game, 目标实体=旧头发实体)
        销毁实体(self.game, 目标实体=旧胡子实体)
        销毁实体(self.game, 目标实体=旧领带实体)
        销毁实体(self.game, 目标实体=旧衣服实体)
        销毁实体(self.game, 目标实体=旧身体实体)
        发送信号(self.game, 信号名="第七关_请求下一位亲戚")
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
        """数据服务下发：本回合来访者数据（关卡级实体生成）。"""
        关卡实体: "实体" = 以GUID查询实体(self.game, GUID=关卡实体GUID)
        if self.owner_entity == 关卡实体:
            pass
        else:
            return

        # 计算生成位置（场地锚点 + 相对偏移）
        场地GUID: "GUID" = 获取节点图变量(self.game, 变量名="游戏场地GUID")
        场地实体: "实体" = 以GUID查询实体(self.game, GUID=场地GUID)
        场地位置: "三维向量"
        场地旋转: "三维向量"
        场地位置, 场地旋转 = 获取实体位置与旋转(self.game, 目标实体=场地实体)
        偏移: "三维向量" = 获取节点图变量(self.game, 变量名="亲戚生成相对偏移")
        生成位置: "三维向量" = 三维向量加法(self.game, 三维向量1=场地位置, 三维向量2=偏移)

        # 外观查表：类型文本 -> 索引 -> 元件ID（本图局部变量）
        idx_body_map: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="外观索引_身体")
        idx_hair_map: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="外观索引_头发")
        idx_beard_map: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="外观索引_胡子")
        idx_glasses_map: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="外观索引_眼镜")
        idx_clothes_map: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="外观索引_衣服")
        idx_neckwear_map: "字符串-整数字典" = 获取节点图变量(self.game, 变量名="外观索引_领饰")

        body_table: "元件ID列表" = 获取节点图变量(self.game, 变量名="外观元件表_身体")
        hair_table: "元件ID列表" = 获取节点图变量(self.game, 变量名="外观元件表_头发")
        beard_table: "元件ID列表" = 获取节点图变量(self.game, 变量名="外观元件表_胡子")
        glasses_table: "元件ID列表" = 获取节点图变量(self.game, 变量名="外观元件表_眼镜")
        clothes_table: "元件ID列表" = 获取节点图变量(self.game, 变量名="外观元件表_衣服")
        neckwear_table: "元件ID列表" = 获取节点图变量(self.game, 变量名="外观元件表_领饰")

        body_idx: "整数" = 以键查询字典值(self.game, 字典=idx_body_map, 键=外观_身体)
        hair_idx: "整数" = 以键查询字典值(self.game, 字典=idx_hair_map, 键=外观_头发)
        beard_idx: "整数" = 以键查询字典值(self.game, 字典=idx_beard_map, 键=外观_胡子)
        glasses_idx: "整数" = 以键查询字典值(self.game, 字典=idx_glasses_map, 键=外观_眼镜)
        clothes_idx: "整数" = 以键查询字典值(self.game, 字典=idx_clothes_map, 键=外观_衣服)
        neckwear_idx: "整数" = 以键查询字典值(self.game, 字典=idx_neckwear_map, 键=外观_领饰)

        身体ID: "元件ID" = 获取列表对应值(self.game, 列表=body_table, 序号=body_idx)
        头发ID: "元件ID" = 获取列表对应值(self.game, 列表=hair_table, 序号=hair_idx)
        胡子ID: "元件ID" = 获取列表对应值(self.game, 列表=beard_table, 序号=beard_idx)
        眼镜ID: "元件ID" = 获取列表对应值(self.game, 列表=glasses_table, 序号=glasses_idx)
        衣服ID: "元件ID" = 获取列表对应值(self.game, 列表=clothes_table, 序号=clothes_idx)
        领饰ID: "元件ID" = 获取列表对应值(self.game, 列表=neckwear_table, 序号=neckwear_idx)

        身体实体: "实体" = 创建元件(
            self.game,
            元件ID=身体ID,
            位置=生成位置,
            拥有者实体=关卡实体,
            是否覆写等级=False,
            等级=1,
            单位标签索引列表=(),
        )
        设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_身体实体", 变量值=身体实体, 是否触发事件=False)

        # 身体就是出生点：其余组件不再使用跟随运动器挂接，统一在出生点附近固定创建。
        组件偏移_头发领带: "三维向量" = 创建三维向量(self.game, X分量=0.0, Y分量=0.0, Z分量=-0.4)
        组件偏移_其他: "三维向量" = 创建三维向量(self.game, X分量=0.0, Y分量=0.0, Z分量=-0.34)
        组件生成位置_头发领带: "三维向量" = 三维向量加法(self.game, 三维向量1=生成位置, 三维向量2=组件偏移_头发领带)
        组件生成位置_其他: "三维向量" = 三维向量加法(self.game, 三维向量1=生成位置, 三维向量2=组件偏移_其他)

        # 眼镜（映射到“眼睛元件”；0 表示不生成）
        零元件ID: "元件ID" = 0
        不生成眼镜: "布尔值" = 是否相等(self.game, 输入1=眼镜ID, 输入2=零元件ID)
        if 不生成眼镜:
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_眼睛实体", 变量值=0, 是否触发事件=False)
        else:
            眼睛实体: "实体" = 创建元件(
                self.game,
                元件ID=眼镜ID,
                位置=组件生成位置_其他,
                拥有者实体=关卡实体,
                是否覆写等级=False,
                等级=1,
                单位标签索引列表=(),
            )
            设置自定义变量(
                self.game,
                目标实体=关卡实体,
                变量名="第七关_亲戚_眼睛实体",
                变量值=眼睛实体,
                是否触发事件=False,
            )

        # 头发（0 表示不生成）
        不生成头发: "布尔值" = 是否相等(self.game, 输入1=头发ID, 输入2=零元件ID)
        if 不生成头发:
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_头发实体", 变量值=0, 是否触发事件=False)
        else:
            头发实体: "实体" = 创建元件(
                self.game,
                元件ID=头发ID,
                位置=组件生成位置_头发领带,
                拥有者实体=关卡实体,
                是否覆写等级=False,
                等级=1,
                单位标签索引列表=(),
            )
            设置自定义变量(
                self.game,
                目标实体=关卡实体,
                变量名="第七关_亲戚_头发实体",
                变量值=头发实体,
                是否触发事件=False,
            )

        # 胡子（0 表示不生成）
        不生成胡子: "布尔值" = 是否相等(self.game, 输入1=胡子ID, 输入2=零元件ID)
        if 不生成胡子:
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_胡子实体", 变量值=0, 是否触发事件=False)
        else:
            胡子实体: "实体" = 创建元件(
                self.game,
                元件ID=胡子ID,
                位置=组件生成位置_其他,
                拥有者实体=关卡实体,
                是否覆写等级=False,
                等级=1,
                单位标签索引列表=(),
            )
            设置自定义变量(
                self.game,
                目标实体=关卡实体,
                变量名="第七关_亲戚_胡子实体",
                变量值=胡子实体,
                是否触发事件=False,
            )

        # 领饰（映射到“领带元件”；0 表示不生成）
        不生成领带: "布尔值" = 是否相等(self.game, 输入1=领饰ID, 输入2=零元件ID)
        if 不生成领带:
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_领带实体", 变量值=0, 是否触发事件=False)
        else:
            领带实体: "实体" = 创建元件(
                self.game,
                元件ID=领饰ID,
                位置=组件生成位置_头发领带,
                拥有者实体=关卡实体,
                是否覆写等级=False,
                等级=1,
                单位标签索引列表=(),
            )
            设置自定义变量(
                self.game,
                目标实体=关卡实体,
                变量名="第七关_亲戚_领带实体",
                变量值=领带实体,
                是否触发事件=False,
            )

        # 衣服（0 表示不生成）
        不生成衣服: "布尔值" = 是否相等(self.game, 输入1=衣服ID, 输入2=零元件ID)
        if 不生成衣服:
            设置自定义变量(self.game, 目标实体=关卡实体, 变量名="第七关_亲戚_衣服实体", 变量值=0, 是否触发事件=False)
        else:
            衣服实体: "实体" = 创建元件(
                self.game,
                元件ID=衣服ID,
                位置=组件生成位置_其他,
                拥有者实体=关卡实体,
                是否覆写等级=False,
                等级=1,
                单位标签索引列表=(),
            )
            设置自定义变量(
                self.game,
                目标实体=关卡实体,
                变量名="第七关_亲戚_衣服实体",
                变量值=衣服实体,
                是否触发事件=False,
            )

        # 开门（亲戚出现）
        # 教程亲戚（亲戚ID=tutorial）由进入第七关时已手动开门，此处不重复开门避免音效/抖动。
        if 亲戚ID == "tutorial":
            pass
        else:
            发送信号(self.game, 信号名=信号名_门动作, 目标状态="打开")
        return

    def register_handlers(self):
        self.game.register_event_handler(
            "定时器触发时",
            self.on_定时器触发时,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_门_动作",
            self.on_第七关_门_动作,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_门_关闭完成",
            self.on_第七关_门_关闭完成,
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

