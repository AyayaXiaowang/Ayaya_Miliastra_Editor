from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取物件属性",
    category="查询节点",
    inputs=[("物件实体", "实体")],
    outputs=[("等级", "整数"), ("当前生命值", "浮点数"), ("上限生命值", "浮点数"), ("当前攻击力", "浮点数"), ("基础攻击力", "浮点数"), ("当前防御力", "浮点数"), ("基础防御力", "浮点数")],
    description="获取物件的相关基础属性",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取物件属性(game, 物件实体):
    """获取物件的相关基础属性"""
    # 本地测试（MockRuntime）最小语义：
    # - 允许通过自定义变量注入各属性（变量名与端口显示名一致）；
    # - 未设置时回退为 0。
    get_custom = getattr(game, "get_custom_variable", None)
    if not callable(get_custom):
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    等级 = int(get_custom(物件实体, "等级", 0) or 0)
    当前生命值 = float(get_custom(物件实体, "当前生命值", 0.0) or 0.0)
    上限生命值 = float(get_custom(物件实体, "上限生命值", 0.0) or 0.0)
    当前攻击力 = float(get_custom(物件实体, "当前攻击力", 0.0) or 0.0)
    基础攻击力 = float(get_custom(物件实体, "基础攻击力", 0.0) or 0.0)
    当前防御力 = float(get_custom(物件实体, "当前防御力", 0.0) or 0.0)
    基础防御力 = float(get_custom(物件实体, "基础防御力", 0.0) or 0.0)
    return 等级, 当前生命值, 上限生命值, 当前攻击力, 基础攻击力, 当前防御力, 基础防御力
