"""
graph_id: server_calibration_enum_coverage_v1
graph_name: 校准_枚举覆盖_server_v1
graph_type: server
description: 枚举覆盖夹具：用于单元测试收集字符串字面量覆盖节点库枚举候选。
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

# ---------------------------- 枚举覆盖字面量（测试用） ----------------------------
ENUM_LITERALS: tuple[str, ...] = (
    '不可刷新',
    '世界坐标系',
    '丢弃',
    '主动关闭',
    '使用',
    '倒下原因_正常被击倒',
    '倒下原因_节点图导致',
    '倒下原因_非正常被击倒',
    '元素类型_冰元素',
    '元素类型_岩元素',
    '元素类型_无',
    '元素类型_水元素',
    '元素类型_火元素',
    '元素类型_草元素',
    '元素类型_雷元素',
    '元素类型_风元素',
    '先快后慢',
    '先慢后快',
    '全员一份',
    '全量刷新',
    '其它单位状态顶替',
    '冻结',
    '匀速直线运动',
    '匹配游玩',
    '取整逻辑_向上取整',
    '取整逻辑_向下取整',
    '取整逻辑_四舍五入',
    '取整逻辑_截尾取整',
    '受保护状态',
    '商店交易',
    '固定时间',
    '固定速度',
    '失败',
    '失败，其它异常',
    '失败，让位于其它状态',
    '失败，超出并存上限',
    '失败，附加叠层未成功',
    '完全跟随',
    '定量刷新',
    '实体类型_关卡',
    '实体类型_物件',
    '实体类型_玩家',
    '实体类型_角色',
    '实体类型_造物',
    '感电',
    '成功，施加新状态',
    '成功，槽位叠层',
    '房间游玩',
    '所有同名并存状态',
    '手柄',
    '技能1-E',
    '技能2-Q',
    '技能3-R',
    '技能4-T',
    '抗打断状态',
    '护盾含量归零',
    '拾取',
    '排序规则_逆序',
    '排序规则_顺序',
    '无跳字',
    '易受打断状态',
    '普通攻击',
    '普通跳字',
    '暴击跳字',
    '最快丢失叠加层数的状态',
    '未定',
    '每人一份',
    '比较运算_大于',
    '比较运算_大于等于',
    '比较运算_小于',
    '比较运算_小于等于',
    '比较运算_相等',
    '潮湿',
    '燃烧',
    '状态失效',
    '玩家完成',
    '界面控件组状态_关闭',
    '界面控件组状态_开启',
    '界面控件组状态_隐藏',
    '相对坐标系',
    '瞬间移动',
    '线性衰减',
    '绽放',
    '职业变更',
    '胜利',
    '自定义技能槽位1',
    '自定义技能槽位10',
    '自定义技能槽位11',
    '自定义技能槽位12',
    '自定义技能槽位13',
    '自定义技能槽位14',
    '自定义技能槽位15',
    '自定义技能槽位2',
    '自定义技能槽位3',
    '自定义技能槽位4',
    '自定义技能槽位5',
    '自定义技能槽位6',
    '自定义技能槽位7',
    '自定义技能槽位8',
    '自定义技能槽位9',
    '节点图关闭',
    '节点图操作',
    '蒸发',
    '融化',
    '被击倒掉落',
    '被驱散',
    '视野优先',
    '触屏',
    '词条失效',
    '试玩',
    '超出持续时间',
    '超时关闭',
    '超载',
    '距离优先',
    '跟随位置',
    '跟随旋转',
    '部分刷新',
    '销毁',
    '键盘鼠标',
    '默认',
)

class 校准_枚举覆盖_server_v1:
    """校准_枚举覆盖_server_v1（server）：仅用于静态测试收集字符串字面量。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        _ = ENUM_LITERALS
        return


    def register_handlers(self):
        self.game.register_event_handler("实体创建时", self.on_实体创建时, owner=self.owner_entity)


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))
