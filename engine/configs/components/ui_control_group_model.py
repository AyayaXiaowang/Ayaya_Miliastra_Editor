"""
界面控件组数据模型
基于知识库：概念介绍/高级概念/界面控件组
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


# ============================================================================
# 固有控件类型定义
# ============================================================================

BUILTIN_WIDGET_TYPES = [
    "小地图",
    "技能区", 
    "队伍信息",
    "角色生命值条",
    "摇杆",
    "造物生命值条",
    "退出按钮",
    "选项卡",
    "聊天按钮",
    "网络状态",
    "挣扎按钮"
]

# ============================================================================
# 通用控件模板类型定义  
# ============================================================================

TEMPLATE_WIDGET_TYPES = [
    "交互按钮",
    "道具展示",
    "文本框",
    "弹窗",
    "进度条",
    "计时器",
    "计分板",
    "卡牌选择器"
]


# ============================================================================
# 单个界面控件配置
# ============================================================================

@dataclass
class UIWidgetConfig:
    """单个界面控件配置"""
    widget_id: str  # 控件唯一ID（索引）
    widget_type: str  # 控件类型
    widget_name: str  # 控件显示名称
    position: Tuple[float, float] = (0.0, 0.0)  # 位置（相对于父容器，像素）
    size: Tuple[float, float] = (100.0, 100.0)  # 尺寸（像素）
    initial_visible: bool = True  # 初始可见性
    layer_index: int = 0  # 显示层级
    is_builtin: bool = False  # 是否为固有控件
    settings: Dict[str, Any] = field(default_factory=dict)  # 类型特定的配置
    
    def serialize(self) -> dict:
        """序列化为字典"""
        return {
            "widget_id": self.widget_id,
            "widget_type": self.widget_type,
            "widget_name": self.widget_name,
            "position": list(self.position),
            "size": list(self.size),
            "initial_visible": self.initial_visible,
            "layer_index": self.layer_index,
            "is_builtin": self.is_builtin,
            "settings": self.settings
        }
    
    @staticmethod
    def deserialize(data: dict) -> UIWidgetConfig:
        """从字典反序列化"""
        return UIWidgetConfig(
            widget_id=data["widget_id"],
            widget_type=data["widget_type"],
            widget_name=data["widget_name"],
            position=tuple(data.get("position", [0.0, 0.0])),
            size=tuple(data.get("size", [100.0, 100.0])),
            initial_visible=data.get("initial_visible", True),
            layer_index=data.get("layer_index", 0),
            is_builtin=data.get("is_builtin", False),
            settings=data.get("settings", {})
        )


# ============================================================================
# 界面控件组模板
# ============================================================================

@dataclass
class UIControlGroupTemplate:
    """界面控件组模板（可以是单个控件或多个控件的组合）"""
    template_id: str  # 模板唯一ID（索引）
    template_name: str  # 模板名称
    is_combination: bool = False  # 是否为组合（多个控件）
    widgets: List[UIWidgetConfig] = field(default_factory=list)  # 包含的控件列表
    group_position: Tuple[float, float] = (0.0, 0.0)  # 组整体位置（相对于画布）
    group_size: Tuple[float, float] = (100.0, 100.0)  # 组整体尺寸
    description: str = ""  # 描述
    created_at: str = ""  # 创建时间
    updated_at: str = ""  # 更新时间
    
    def serialize(self) -> dict:
        """序列化为字典"""
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "is_combination": self.is_combination,
            "widgets": [w.serialize() for w in self.widgets],
            "group_position": list(self.group_position),
            "group_size": list(self.group_size),
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @staticmethod
    def deserialize(data: dict) -> UIControlGroupTemplate:
        """从字典反序列化"""
        # 容错处理：如果缺少必需字段，返回None或抛出更友好的错误
        if "template_id" not in data:
            # 如果数据格式错误，生成一个临时ID（通常不应该发生）
            import warnings
            warnings.warn(f"UI控件模板数据缺少template_id字段，数据将被跳过: {data.get('name', 'unknown')}")
            return None
        
        return UIControlGroupTemplate(
            template_id=data["template_id"],
            template_name=data["template_name"],
            is_combination=data.get("is_combination", False),
            widgets=[UIWidgetConfig.deserialize(w) for w in data.get("widgets", [])],
            group_position=tuple(data.get("group_position", [0.0, 0.0])),
            group_size=tuple(data.get("group_size", [100.0, 100.0])),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )


# ============================================================================
# 界面布局配置
# ============================================================================

@dataclass
class UILayout:
    """界面布局（一个完整的UI界面配置）"""
    layout_id: str  # 布局唯一ID
    layout_name: str  # 布局名称
    builtin_widgets: List[str] = field(default_factory=list)  # 固有内容控件组ID列表（不可删除）
    custom_groups: List[str] = field(default_factory=list)  # 自定义控件组ID列表
    default_for_player: Optional[str] = None  # 默认应用的玩家类型（可选）
    description: str = ""  # 描述
    created_at: str = ""  # 创建时间
    updated_at: str = ""  # 更新时间
    visibility_overrides: Dict[str, bool] = field(default_factory=dict)  # 布局局部显隐覆盖
    
    def serialize(self) -> dict:
        """序列化为字典"""
        return {
            "layout_id": self.layout_id,
            "layout_name": self.layout_name,
            "builtin_widgets": self.builtin_widgets,
            "custom_groups": self.custom_groups,
            "default_for_player": self.default_for_player,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "visibility_overrides": self.visibility_overrides,
        }
    
    @staticmethod
    def deserialize(data: dict) -> UILayout:
        """从字典反序列化"""
        return UILayout(
            layout_id=data["layout_id"],
            layout_name=data["layout_name"],
            builtin_widgets=data.get("builtin_widgets", []),
            custom_groups=data.get("custom_groups", []),
            default_for_player=data.get("default_for_player"),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            visibility_overrides=data.get("visibility_overrides", {}),
        )


# ============================================================================
# 设备预设
# ============================================================================

@dataclass
class DevicePreset:
    """设备预设配置"""
    name: str  # 设备名称
    width: int  # 宽度（像素）
    height: int  # 高度（像素）
    dpi: int = 96  # DPI
    category: str = "手机"  # 分类：手机、平板、PC


# 设备预设（按照官方定义的设备类型和比例）
DEVICE_PRESETS = [
    # PC
    DevicePreset("PC 16:9", 1920, 1080, 96, "PC"),
    DevicePreset("PC 21:9", 2560, 1080, 96, "PC"),
    
    # 触摸
    DevicePreset("触摸 16:9", 1920, 1080, 160, "触摸"),
    DevicePreset("触摸 19.5:9", 2340, 1080, 160, "触摸"),
    DevicePreset("触摸 4:3", 1440, 1080, 160, "触摸"),
    
    # 手柄1
    DevicePreset("手柄1 16:9", 1920, 1080, 96, "手柄1"),
    DevicePreset("手柄1 21:9", 2560, 1080, 96, "手柄1"),
    
    # 手柄2
    DevicePreset("手柄2 16:9", 1920, 1080, 160, "手柄2"),
    DevicePreset("手柄2 19.5:9", 2340, 1080, 160, "手柄2"),
    DevicePreset("手柄2 4:3", 1440, 1080, 160, "手柄2"),
]


# ============================================================================
# 初始化函数
# ============================================================================

def create_default_layout() -> UILayout:
    """创建默认界面布局"""
    now = datetime.now().isoformat()
    
    # 创建默认布局
    layout = UILayout(
        layout_id="layout_default",
        layout_name="默认布局",
        builtin_widgets=[],  # 稍后会添加固有控件
        custom_groups=[],
        default_for_player="所有玩家",
        description="默认的界面布局，包含所有必要的固有控件",
        created_at=now,
        updated_at=now
    )
    
    return layout


def create_builtin_widget_templates() -> Dict[str, UIControlGroupTemplate]:
    """创建所有固有控件模板"""
    now = datetime.now().isoformat()
    templates = {}
    
    # 固有控件的默认位置和大小配置
    builtin_configs = {
        "小地图": {"position": (50, 50), "size": (200, 200)},
        "技能区": {"position": (1600, 900), "size": (250, 120)},
        "队伍信息": {"position": (10, 300), "size": (180, 400)},
        "角色生命值条": {"position": (860, 950), "size": (200, 50)},
        "摇杆": {"position": (150, 800), "size": (180, 180)},
        "造物生命值条": {"position": (860, 850), "size": (200, 50)},
        "退出按钮": {"position": (1820, 20), "size": (80, 80)},
        "选项卡": {"position": (1820, 120), "size": (80, 300)},
        "聊天按钮": {"position": (1700, 20), "size": (80, 80)},
        "网络状态": {"position": (1580, 20), "size": (100, 40)},
        "挣扎按钮": {"position": (860, 540), "size": (200, 80)}
    }
    
    for idx, widget_type in enumerate(BUILTIN_WIDGET_TYPES):
        template_id = f"builtin_{widget_type}"
        config = builtin_configs.get(widget_type, {"position": (0, 0), "size": (100, 100)})
        
        # 创建单个控件
        widget = UIWidgetConfig(
            widget_id=f"{template_id}_widget",
            widget_type=widget_type,
            widget_name=widget_type,
            position=config["position"],
            size=config["size"],
            initial_visible=True,
            layer_index=idx,
            is_builtin=True,
            settings={}
        )
        
        # 创建模板（固有控件都是单控件模板）
        template = UIControlGroupTemplate(
            template_id=template_id,
            template_name=widget_type,
            is_combination=False,
            widgets=[widget],
            group_position=config["position"],
            group_size=config["size"],
            description=f"固有内容：{widget_type}",
            created_at=now,
            updated_at=now
        )
        
        templates[template_id] = template
    
    return templates


def create_template_widget_preset(widget_type: str) -> UIControlGroupTemplate:
    """创建通用控件模板预设"""
    now = datetime.now().isoformat()
    template_id = f"template_{widget_type}_{int(datetime.now().timestamp() * 1000)}"
    
    # 默认配置
    default_settings = {}
    default_size = (200, 100)
    
    # 根据控件类型设置不同的默认值
    if widget_type == "交互按钮":
        default_size = (120, 60)
        default_settings = {
            "button_type": "交互事件",
            "button_text": "按钮",
            "icon": None,
            "cooldown": 0.0
        }
    elif widget_type == "道具展示":
        default_size = (80, 80)
        default_settings = {
            "display_type": "背包内道具",
            "can_interact": True
        }
    elif widget_type == "文本框":
        default_size = (300, 50)
        default_settings = {
            "background_color": "黑色半透明",
            "font_size": 16,
            "text_content": "文本内容",
            "alignment_h": "左侧对齐",
            "alignment_v": "顶部对齐"
        }
    elif widget_type == "弹窗":
        default_size = (600, 400)
        default_settings = {
            "title": "标题",
            "content": "内容",
            "buttons": []
        }
    elif widget_type == "进度条":
        default_size = (300, 30)
        default_settings = {
            "shape": "横向",
            "style": "百分比",
            "color": "#00FF00",
            "current_var": None,
            "min_var": None,
            "max_var": None
        }
    elif widget_type == "计时器":
        default_size = (200, 60)
        default_settings = {
            "timer_type": "倒计时",
            "timer_id": None,
            "source_entity": "关卡实体"
        }
    elif widget_type == "计分板":
        default_size = (400, 600)
        default_settings = {
            "board_type": "个人",
            "sort_order": "降序",
            "key_mapping": None
        }
    elif widget_type == "卡牌选择器":
        default_size = (800, 600)
        default_settings = {
            "cards": [],
            "selection_mode": "单选"
        }
    
    # 创建控件
    widget = UIWidgetConfig(
        widget_id=f"{template_id}_widget",
        widget_type=widget_type,
        widget_name=widget_type,
        position=(0, 0),
        size=default_size,
        initial_visible=True,
        layer_index=0,
        is_builtin=False,
        settings=default_settings
    )
    
    # 创建模板
    template = UIControlGroupTemplate(
        template_id=template_id,
        template_name=f"新建{widget_type}",
        is_combination=False,
        widgets=[widget],
        group_position=(100, 100),
        group_size=default_size,
        description=f"{widget_type}模板",
        created_at=now,
        updated_at=now
    )
    
    return template


if __name__ == "__main__":
    print("=== 界面控件组数据模型测试 ===\n")
    
    # 测试创建默认布局
    print("1. 创建默认布局：")
    layout = create_default_layout()
    print(f"   布局ID: {layout.layout_id}")
    print(f"   布局名称: {layout.layout_name}")
    
    # 测试创建固有控件
    print("\n2. 创建固有控件模板：")
    builtin_templates = create_builtin_widget_templates()
    print(f"   固有控件数量: {len(builtin_templates)}")
    for template_id, template in list(builtin_templates.items())[:3]:
        print(f"   - {template.template_name}: 位置{template.group_position}, 大小{template.group_size}")
    
    # 测试创建通用控件
    print("\n3. 创建通用控件模板：")
    button_template = create_template_widget_preset("交互按钮")
    print(f"   模板ID: {button_template.template_id}")
    print(f"   模板名称: {button_template.template_name}")
    print(f"   控件数量: {len(button_template.widgets)}")
    print(f"   默认设置: {button_template.widgets[0].settings}")
    
    # 测试序列化和反序列化
    print("\n4. 测试序列化：")
    serialized = button_template.serialize()
    print(f"   序列化成功，字段数: {len(serialized)}")
    
    deserialized = UIControlGroupTemplate.deserialize(serialized)
    print(f"   反序列化成功: {deserialized.template_name}")
    
    # 测试设备预设
    print("\n5. 设备预设：")
    print(f"   可用设备数量: {len(DEVICE_PRESETS)}")
    for device in DEVICE_PRESETS[:5]:
        print(f"   - {device.name} ({device.category}): {device.width}x{device.height}")
    
    print("\n✅ 界面控件组数据模型测试完成")

