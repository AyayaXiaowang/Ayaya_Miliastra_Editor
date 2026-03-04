"""
graph_id: server_test_project_level7_relatives_data_service
graph_name: 数据元件实体_第七关_亲戚数据服务
graph_type: server
description: 第七关“真假亲戚”数据服务（与 UI 游戏中节点图解耦）：

- 数据来源：数据存放元件（模板自定义变量：扁平列表 + 指针）。
- 开局：监听信号 `第七关_开始游戏`，随机选择一局 round 并下发妈妈纸条（`第七关_下发本局纸条`）。
- 每回合：监听信号 `第七关_请求下一位亲戚`，按出场顺序取一位来访者并下发关键数据（`第七关_下发亲戚数据`）。

数据结构（自定义变量）：
- `l7_rounds_count`：整数，本元件内共有多少局 round。
- `l7_clue_title`：字符串（妈妈纸条标题）。
- `l7_clue_tags_flat` / `l7_clue_texts_flat`：字符串列表，长度 = rounds_count * 6。
- `l7_visit_role_flat` / `l7_visit_truth_flat` / `l7_visit_*_flat`：每个字段一个扁平列表，长度 = rounds_count * 10。
- `l7_visit_dlg_l1_flat`~`l7_visit_dlg_l4_flat`：字符串列表，长度 = rounds_count * 10（每位亲戚固定 4 句对白；文本只保留“说话内容”，不带“称谓：”前缀）。
- `l7_sel_round_idx`：整数，本局选中的 round 序号。
- `l7_visit_i`：整数，本局来访序号（0~9，循环）。
- 挂载实体：第七关数据存放元件实体（即保存 `l7_*` 扁平数据变量的实体）。
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


VAR_ROUNDS_COUNT: "字符串" = "l7_rounds_count"
VAR_CLUE_TITLE: "字符串" = "l7_clue_title"
VAR_CLUE_TAGS_FLAT: "字符串" = "l7_clue_tags_flat"
VAR_CLUE_TEXTS_FLAT: "字符串" = "l7_clue_texts_flat"

VAR_VISIT_ROLE_FLAT: "字符串" = "l7_visit_role_flat"
VAR_VISIT_TRUTH_ALLOW_FLAT: "字符串" = "l7_visit_truth_flat"
VAR_VISIT_BODY_FLAT: "字符串" = "l7_visit_body_flat"
VAR_VISIT_HAIR_FLAT: "字符串" = "l7_visit_hair_flat"
VAR_VISIT_BEARD_FLAT: "字符串" = "l7_visit_beard_flat"
VAR_VISIT_GLASSES_FLAT: "字符串" = "l7_visit_glass_flat"
VAR_VISIT_CLOTHES_FLAT: "字符串" = "l7_visit_cloth_flat"
VAR_VISIT_NECKWEAR_FLAT: "字符串" = "l7_visit_neck_flat"
VAR_VISIT_DIALOGUE_L1_FLAT: "字符串" = "l7_visit_dlg_l1_flat"
VAR_VISIT_DIALOGUE_L2_FLAT: "字符串" = "l7_visit_dlg_l2_flat"
VAR_VISIT_DIALOGUE_L3_FLAT: "字符串" = "l7_visit_dlg_l3_flat"
VAR_VISIT_DIALOGUE_L4_FLAT: "字符串" = "l7_visit_dlg_l4_flat"

VAR_SELECTED_INDEX: "字符串" = "l7_sel_round_idx"
VAR_VISIT_I: "字符串" = "l7_visit_i"

CLUES_PER_ROUND: "整数" = 6
VISITS_PER_ROUND: "整数" = 10


class 数据元件实体_第七关_亲戚数据服务:
    def __init__(self, game: GameRuntime, owner_entity: "实体"):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_第七关_开始游戏(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
    ) -> None:
        store: "实体" = self.owner_entity

        total: "整数" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_ROUNDS_COUNT)
        max_idx: "整数" = (total - 1)
        idx: "整数" = 获取随机整数(self.game, 下限=0, 上限=max_idx)

        last_idx: "整数" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_SELECTED_INDEX)
        if (total > 1) and (idx == last_idx):
            idx2: "整数" = (idx + 1)
            idx = 模运算(self.game, 被模数=idx2, 模数=total)

        设置自定义变量(self.game, 目标实体=store, 变量名=VAR_SELECTED_INDEX, 变量值=idx, 是否触发事件=False)
        设置自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_I, 变量值=0, 是否触发事件=False)

        clue_title: "字符串" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_CLUE_TITLE)
        clue_tags_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_CLUE_TAGS_FLAT)
        clue_texts_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_CLUE_TEXTS_FLAT)

        base: "整数" = (idx * CLUES_PER_ROUND)

        i0: "整数" = base
        i1: "整数" = (base + 1)
        i2: "整数" = (base + 2)
        i3: "整数" = (base + 3)
        i4: "整数" = (base + 4)
        i5: "整数" = (base + 5)

        tag1: "字符串" = clue_tags_flat[i0]
        tag2: "字符串" = clue_tags_flat[i1]
        tag3: "字符串" = clue_tags_flat[i2]
        tag4: "字符串" = clue_tags_flat[i3]
        tag5: "字符串" = clue_tags_flat[i4]
        tag6: "字符串" = clue_tags_flat[i5]

        text1: "字符串" = clue_texts_flat[i0]
        text2: "字符串" = clue_texts_flat[i1]
        text3: "字符串" = clue_texts_flat[i2]
        text4: "字符串" = clue_texts_flat[i3]
        text5: "字符串" = clue_texts_flat[i4]
        text6: "字符串" = clue_texts_flat[i5]

        clue_tags: "字符串列表" = [tag1, tag2, tag3, tag4, tag5, tag6]
        clue_texts: "字符串列表" = [text1, text2, text3, text4, text5, text6]

        发送信号(
            self.game,
            信号名="第七关_下发本局纸条",
            线索标题=clue_title,
            线索标签列表=clue_tags,
            线索文本列表=clue_texts,
        )
        return

    def on_第七关_请求下一位亲戚(
        self,
        事件源实体: "实体",
        事件源GUID: "GUID",
        信号来源实体: "实体",
    ) -> None:
        store: "实体" = self.owner_entity

        round_i: "整数" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_SELECTED_INDEX)
        visit_i: "整数" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_I)

        base_i: "整数" = (round_i * VISITS_PER_ROUND)
        idx: "整数" = (base_i + visit_i)
        pid: "字符串" = str(idx)

        role_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_ROLE_FLAT)
        truth_flat: "布尔值列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_TRUTH_ALLOW_FLAT)
        body_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_BODY_FLAT)
        hair_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_HAIR_FLAT)
        beard_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_BEARD_FLAT)
        glasses_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_GLASSES_FLAT)
        clothes_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_CLOTHES_FLAT)
        neckwear_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_NECKWEAR_FLAT)
        dialogue_l1_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_DIALOGUE_L1_FLAT)
        dialogue_l2_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_DIALOGUE_L2_FLAT)
        dialogue_l3_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_DIALOGUE_L3_FLAT)
        dialogue_l4_flat: "字符串列表" = 获取自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_DIALOGUE_L4_FLAT)

        role: "字符串" = role_flat[idx]
        truth_allow: "布尔值" = truth_flat[idx]
        body: "字符串" = body_flat[idx]
        hair: "字符串" = hair_flat[idx]
        beard: "字符串" = beard_flat[idx]
        glasses: "字符串" = glasses_flat[idx]
        clothes: "字符串" = clothes_flat[idx]
        neckwear: "字符串" = neckwear_flat[idx]

        line1: "字符串" = dialogue_l1_flat[idx]
        line2: "字符串" = dialogue_l2_flat[idx]
        line3: "字符串" = dialogue_l3_flat[idx]
        line4: "字符串" = dialogue_l4_flat[idx]
        dialogue_lines: "字符串列表" = [line1, line2, line3, line4]

        发送信号(
            self.game,
            信号名="第七关_下发亲戚数据",
            亲戚ID=pid,
            称谓=role,
            真相为允许=truth_allow,
            外观_身体=body,
            外观_头发=hair,
            外观_胡子=beard,
            外观_眼镜=glasses,
            外观_衣服=clothes,
            外观_领饰=neckwear,
            对白列表=dialogue_lines,
        )

        next_i_raw: "整数" = (visit_i + 1)
        need_wrap: "布尔值" = (next_i_raw >= VISITS_PER_ROUND)
        if need_wrap:
            next_i: "整数" = 0
        else:
            next_i: "整数" = next_i_raw
        设置自定义变量(self.game, 目标实体=store, 变量名=VAR_VISIT_I, 变量值=next_i, 是否触发事件=False)
        return

    def register_handlers(self):
        # 信号事件名在 Graph Code 侧直接使用“显示名称”（signal_name）。
        self.game.register_event_handler(
            "第七关_开始游戏",
            self.on_第七关_开始游戏,
            owner=self.owner_entity,
        )
        self.game.register_event_handler(
            "第七关_请求下一位亲戚",
            self.on_第七关_请求下一位亲戚,
            owner=self.owner_entity,
        )


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

