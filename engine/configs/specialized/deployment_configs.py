"""
实体布设组与数据复制粘贴配置。
从 `extended_configs.py` 聚合文件中拆分而来，现作为专门模块使用。
"""
from dataclasses import dataclass, field
from typing import List


# ============================================================================
# 基础信息扩展 (实体布设组、数据复制粘贴)
# ============================================================================

@dataclass
class EntityDeploymentGroup:
    """
    实体布设组配置
    参考：实体布设组.md
    
    用于批量管理布设实体，可以通过节点实现批量创建和销毁
    """
    group_name: str = ""  # 实体布设组名称
    group_index: str = ""  # 索引（唯一标识）
    initial_create: bool = True  # 初始创建：该布设组内的地形和静态物件是否随关卡一同创建
    entity_list: List[str] = field(default_factory=list)  # 内容列表：包含的所有单位
    
    # 支持的单位类型：造物、角色、物件、地形
    supported_entity_types: List[str] = field(default_factory=lambda: ["造物", "角色", "物件", "地形"])
    
    doc_reference: str = "实体布设组.md"
    
    notes: str = """
    功能说明：
    1. 批量管理布设实体
    2. 可通过节点批量创建和销毁
    3. 快速定位所有属于该组的单位
    4. 同一个实体可以归属于多个实体布设组
    """


@dataclass
class DataCopyPasteConfig:
    """
    数据复制粘贴配置
    参考：数据复制粘贴.md
    
    用于复制指定内容的数据，存于独立剪贴板内，后续可粘贴并替换目标内容的数据
    """
    # 使用限制
    supported_asset_types: List[str] = field(default_factory=lambda: ["物件", "造物"])
    
    # 元件数据复制粘贴
    component_copy_paste_enabled: bool = True
    # 实体数据复制粘贴
    entity_copy_paste_enabled: bool = True
    
    # 数据替换规则
    excluded_fields: List[str] = field(default_factory=lambda: [
        "名称", "id", "GUID", "辨识码", "归属页签"
    ])
    
    doc_reference: str = "数据复制粘贴.md"
    
    notes: str = """
    使用对象：
    - 元件数据仅可粘贴于元件
    - 实体数据仅可粘贴于实体
    
    数据替换：
    - 除名称、id（辨识码）、归属页签外的所有数据
    - 所有附属实体的数据
    """

