"""
graph_id: client_calibration_enum_coverage_v1
graph_name: 校准_枚举覆盖_client_v1
graph_type: client
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

from app.runtime.engine.graph_prelude_client import *  # noqa: F401,F403

# ---------------------------- 枚举覆盖字面量（测试用） ----------------------------
ENUM_LITERALS: tuple[str, ...] = (
    '不满足条件',
    '从近到远排序',
    '候选目标',
    '元素类型_冰元素',
    '元素类型_岩元素',
    '元素类型_无',
    '元素类型_水元素',
    '元素类型_火元素',
    '元素类型_草元素',
    '元素类型_雷元素',
    '元素类型_风元素',
    '先目标后输入',
    '先目标后镜头',
    '先输入后目标',
    '全部',
    '全部命中',
    '刺击攻击',
    '剔除自身的全部',
    '友善阵营',
    '友善阵营包括自身',
    '受击反方向',
    '受击盒',
    '只命中受击盒',
    '只命中场景',
    '只触发一次',
    '场景',
    '实体类型_关卡',
    '实体类型_物件',
    '实体类型_玩家',
    '实体类型_角色',
    '实体类型_造物',
    '对于每个实体只触发一次',
    '强力冲击',
    '当前扫描目标',
    '手柄',
    '扰动装置类型_力场器',
    '扰动装置类型_弹射器',
    '扰动装置类型_牵引器',
    '投射物',
    '攻击形状_扇形',
    '攻击形状_球体',
    '攻击形状_矩形',
    '攻击盒命中方向',
    '攻击者与受击点的连线',
    '攻击者与受击点连线切线',
    '攻击者与受击点连线反方向',
    '攻击者主人与受击点连线',
    '攻击者面朝朝向',
    '敌对阵营',
    '斩击',
    '无',
    '无受击表现',
    '普通受击',
    '未蓄力普通箭受击',
    '物件自身碰撞',
    '由内向外',
    '目标不可用',
    '目标朝向',
    '终结技冲击',
    '自己',
    '自身阵营',
    '触屏',
    '输入朝向',
    '近战攻击',
    '远程攻击',
    '连击受击',
    '逆时针',
    '重受击',
    '钝击',
    '键盘鼠标',
    '镜头朝向',
    '随机排序',
    '顺时针',
    '默认',
    '默认排序',
)

class 校准_枚举覆盖_client_v1:
    """校准_枚举覆盖_client_v1（client）：仅用于静态测试收集字符串字面量。"""

    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        from app.runtime.engine.node_graph_validator import validate_node_graph

        validate_node_graph(self.__class__)

    def on_节点图开始(self):
        _ = ENUM_LITERALS
        return


    def register_handlers(self):
        return


if __name__ == "__main__":
    from app.runtime.engine.node_graph_validator import validate_file_cli

    raise SystemExit(validate_file_cli(__file__))
