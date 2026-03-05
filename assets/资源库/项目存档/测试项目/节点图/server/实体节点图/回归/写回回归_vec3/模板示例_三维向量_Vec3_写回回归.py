"""
graph_id: server_template_vec3_writeback_regression_01
graph_name: 模板示例_三维向量_Vec3_写回回归
graph_type: server
description: 三维向量(Vec3) 写回/导出口径回归样例：

- 覆盖 Vec3 数字常量（创建三维向量）/连线输入（Vec 运算结果）/列表（三维向量列表）/字典（字符串-三维向量字典）
- 覆盖 Create_Prefab(创建元件) 的 Vec 端口：位置连线输入、旋转常量/占位
- 该示例不绑定任何项目存档资源：元件ID 由图变量暴露，便于在不同存档中手动替换为可见元件
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


# ---------------------------- 常量（避免魔法数字） ----------------------------
VEC_A_X = 1.25
VEC_A_Y = -2.5
VEC_A_Z = 3.75

VEC_B_X = 10.0
VEC_B_Y = 20.0
VEC_B_Z = 30.0

VEC_OFFSET_UP_Z = 5.0
ZERO_FLOAT = 0.0
ZERO_INT = 0

LEVEL_DEFAULT = 1
DO_NOT_OVERRIDE_LEVEL = False

DICT_KEY_A = "a"
DICT_KEY_B = "b"

LIST_INDEX_0 = 0


GRAPH_VARIABLES: list[GraphVariableConfig] = [
    GraphVariableConfig(
        name="测试_元件ID",
        variable_type="元件ID",
        # 约束：元件ID 的 default_value 必须是可静态解析的 1~10 位纯数字（int 或数字字符串），不可引用变量常量。
        default_value=0,
        description="测试用：用于【创建元件】节点的元件ID；请在目标存档中改成一个可见元件ID。",
        is_exposed=True,
    ),
]


class 模板示例_三维向量_Vec3_写回回归:
    """Vec3 写回/导出口径回归样例（server）"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        # ===== 1) Vec3 数字常量（填写数字）=====
        vec_a: "三维向量" = 创建三维向量(self.game, X分量=VEC_A_X, Y分量=VEC_A_Y, Z分量=VEC_A_Z)
        vec_b: "三维向量" = (VEC_B_X, VEC_B_Y, VEC_B_Z)
        up_offset: "三维向量" = 创建三维向量(self.game, X分量=ZERO_FLOAT, Y分量=ZERO_FLOAT, Z分量=VEC_OFFSET_UP_Z)

        owner_pos: "三维向量"
        owner_rot: "三维向量"
        owner_pos, owner_rot = 获取实体位置与旋转(self.game, 目标实体=self.owner_entity)

        # ===== 2) Vec3 连线输入（Vec 运算结果）=====
        spawn_pos_1: "三维向量" = 三维向量加法(self.game, 三维向量1=owner_pos, 三维向量2=up_offset)
        spawn_pos_2: "三维向量" = 三维向量加法(self.game, 三维向量1=spawn_pos_1, 三维向量2=vec_a)

        # ===== 3) Create_Prefab(创建元件) Vec 端口 =====
        # - 位置：连线输入（spawn_pos_2）
        # - 旋转：常量（vec_b）
        prefab_id: "元件ID" = 获取节点图变量(self.game, 变量名="测试_元件ID")
        _spawn_entity_1: "实体" = 创建元件(
            self.game,
            元件ID=prefab_id,
            位置=spawn_pos_2,
            旋转=vec_b,
            拥有者实体=self.owner_entity,
            是否覆写等级=DO_NOT_OVERRIDE_LEVEL,
            等级=LEVEL_DEFAULT,
            单位标签索引列表=(),
        )

        # 另一条：位置常量（vec_a），旋转连线输入（owner_rot）
        _spawn_entity_2: "实体" = 创建元件(
            self.game,
            元件ID=prefab_id,
            位置=vec_a,
            旋转=(VEC_B_X, VEC_B_Y, VEC_B_Z),
            拥有者实体=self.owner_entity,
            是否覆写等级=DO_NOT_OVERRIDE_LEVEL,
            等级=LEVEL_DEFAULT,
            单位标签索引列表=(),
        )

        # ===== 4) Vec3 列表（拼装列表 + 获取列表对应值）=====
        vec_list: "三维向量列表" = 拼装列表(self.game, vec_a, vec_b, spawn_pos_2)
        vec_first: "三维向量" = 获取列表对应值(self.game, 列表=vec_list, 序号=LIST_INDEX_0)

        # 用列表元素再走一遍创建元件（强化连线链路）
        _spawn_entity_3: "实体" = 创建元件(
            self.game,
            元件ID=prefab_id,
            位置=vec_first,
            旋转=vec_b,
            拥有者实体=self.owner_entity,
            是否覆写等级=DO_NOT_OVERRIDE_LEVEL,
            等级=LEVEL_DEFAULT,
            单位标签索引列表=(),
        )

        # ===== 5) Vec3 字典（字符串-三维向量字典）=====
        # 禁止空字典字面量 {}：用『拼装字典』一次性构造字典（避免“计算节点输出 dict + 原地修改”带来的写回语义问题）。
        vec_dict: "字符串-三维向量字典" = 拼装字典(self.game, DICT_KEY_A, vec_a, DICT_KEY_B, spawn_pos_2)

        # 通过“以键查询字典值”固化 K/V 语义证据，并将结果再用于创建元件
        default_vec: "三维向量" = 创建三维向量(self.game, X分量=ZERO_FLOAT, Y分量=ZERO_FLOAT, Z分量=ZERO_FLOAT)
        dict_vec: "三维向量" = 以键查询字典值(self.game, 字典=vec_dict, 键=DICT_KEY_A)

        _spawn_entity_4: "实体" = 创建元件(
            self.game,
            元件ID=prefab_id,
            位置=dict_vec,
            旋转=vec_b,
            拥有者实体=self.owner_entity,
            是否覆写等级=DO_NOT_OVERRIDE_LEVEL,
            等级=LEVEL_DEFAULT,
            单位标签索引列表=(),
        )
        return

    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))

