"""
组件配置 - 商店
基于知识库文档定义的商店组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class ShopSourceType(Enum):
    """商品来源类型（商店.md 第27行）"""
    OWN_BACKPACK = "自身背包"
    CUSTOM_LIST = "自定义列表"


class ShopTabType(Enum):
    """商品页签类型（商店.md 第20-23行）"""
    NO_TAB = "无页签"
    DEFAULT_TAB = "默认页签"
    CUSTOM_TAB = "自定义页签"


class PurchaseRange(Enum):
    """收购范围（商店.md 第45-48行）"""
    NO_PURCHASE = "不收购"
    ALL_ITEMS = "全部道具"
    PARTIAL_ITEMS = "部分道具"


@dataclass
class ShopDefinition:
    """
    单个商店定义
    来源：商店.md (第13-17行)
    """
    # 商店序号
    shop_index: int
    # 商店名称
    shop_name: str
    # 商店模板（引用全局商店模板配置ID）
    shop_template: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "商店序号": self.shop_index,
            "商店名称": self.shop_name,
            "商店模板": self.shop_template
        }


@dataclass
class ShopComponentConfig:
    """
    商店组件配置
    来源：商店.md (第1-17行)
    注意：商店组件支持同时配置多个商店（第3行）
    """
    # 商店列表
    shops: List[ShopDefinition] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "商店列表": [shop.to_dict() for shop in self.shops]
        }

