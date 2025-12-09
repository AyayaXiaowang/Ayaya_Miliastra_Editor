"""任务清单配置文件

此文件统一管理任务清单UI的所有配置项，包括：
- 任务类型元数据（图标、标签、颜色）
- 详情类型图标映射
- 样式常量
- 端口和布局常量

所有颜色、尺寸、图标等主题相关配置统一在 theme_manager.py 中定义。

修改说明：
- 修改任务类型颜色：编辑 theme_manager.py 中的 Colors 类
- 新增任务类型：在 TaskTypeMetadata.METADATA 添加条目
- 修改图标：编辑 DetailTypeIcons 类
- 修改延迟时间、边距等数值：编辑 TodoStyles 或 LayoutConstants 类
"""

from dataclasses import dataclass

from ui.foundation.theme_manager import (
    Colors as ThemeColors,
    Sizes as ThemeSizes,
    Icons as ThemeIcons,
)


class TaskTypeMetadata:
    """任务类型元数据（统一管理图标、标签、颜色）"""
    
    METADATA = {
        "category": {
            "icon": "▪",
            "label": "分类",
            "color": ThemeColors.CATEGORY,
            "light_color": ThemeColors.CATEGORY_LIGHT,
            "description": {
                "templates": "元件库包含所有可复用的实体元件，每个元件定义了一类实体的默认属性、节点图逻辑、组件配置等。",
                "instances": "实体摆放用于在场景中放置具体的实体，每个实体基于某个元件创建，并可以覆盖部分属性。",
                "combat": "战斗预设定义了游戏的战斗系统配置，包括职业、技能、道具、投射物等。",
                "management": "管理数据包含全局性的系统配置，如计时器、全局变量、预设点等。"
            }
        },
        "template": {
            "icon": "▸",
            "label": "元件配置",
            "color": ThemeColors.TEMPLATE,
            "light_color": ThemeColors.TEMPLATE_LIGHT
        },
        "instance": {
            "icon": "▸",
            "label": "实体摆放",
            "color": ThemeColors.INSTANCE,
            "light_color": ThemeColors.INSTANCE_LIGHT
        },
        "combat": {
            "icon": "•",
            "label": "战斗预设",
            "color": ThemeColors.COMBAT,
            "light_color": ThemeColors.COMBAT_LIGHT
        },
        "management": {
            "icon": "•",
            "label": "管理数据",
            "color": ThemeColors.MANAGEMENT,
            "light_color": ThemeColors.MANAGEMENT_LIGHT
        }
    }
    
    @classmethod
    def get_color(cls, task_type: str) -> str:
        """获取任务类型对应的颜色"""
        return cls.METADATA.get(task_type, {}).get("color", ThemeColors.TEXT_PRIMARY)
    
    @classmethod
    def get_light_color(cls, task_type: str) -> str:
        """获取任务类型对应的浅色"""
        return cls.METADATA.get(task_type, {}).get("light_color", ThemeColors.BORDER_LIGHT)
    
    @classmethod
    def get_label(cls, task_type: str) -> str:
        """获取任务类型对应的标签"""
        return cls.METADATA.get(task_type, {}).get("label", task_type)
    
    @classmethod
    def get_icon(cls, task_type: str) -> str:
        """获取任务类型对应的图标"""
        return cls.METADATA.get(task_type, {}).get("icon", "•")
    
    @classmethod
    def get_category_description(cls, category: str) -> str:
        """获取分类描述"""
        return cls.METADATA.get("category", {}).get("description", {}).get(category, "")


class DetailTypeIcons:
    """详情类型图标映射（根据任务详情类型返回对应图标）"""
    
    # 模板类型图标
    TEMPLATE_ICONS = {
        "template_graph": "◆",
        "template_variable": "◇",
        "template_component": "◦",
        "default": "•"
    }
    
    # 实体类型图标
    INSTANCE_ICONS = {
        "instance_position": "◆",
        "instance_rotation": "◇",
        "default": "•"
    }
    
    # 战斗类型图标
    COMBAT_ICONS = {
        "player": "◆",
        "skill": "◇",
        "item": "◦",
        "default": "•"
    }
    
    # 管理类型图标
    MANAGEMENT_ICONS = {
        "timer": "◆",
        "variable": "◇",
        "default": "•"
    }
    
    # 节点图类型图标
    GRAPH_ICONS = {
        "graph_create_node": "+",
        "graph_connect": "─",
        "graph_config_node": "◦",
        "graph_set_port_types_merged": "◦",
        "graph_add_variadic_inputs": "+",
        "graph_add_dict_pairs": "+",
        "graph_add_branch_outputs": "+",
        "graph_config_branch_outputs": "◦",
        "graph_bind_signal": "◦",
        "graph_bind_struct": "◦",
        "default": "◆",
    }
    
    # 复合节点类型图标
    COMPOSITE_ICONS = {
        "composite_root": "◆",
        "composite_create_new": "+",
        "composite_set_meta": "◦",
        "composite_set_pins": "◇",
        "composite_save": "✓",
        "default": "•"
    }
    
    @classmethod
    def get_icon(cls, task_type: str, detail_info: dict) -> str:
        """根据任务类型和详情信息获取图标
        
        Args:
            task_type: 任务类型（category, template, instance等）
            detail_info: 任务详情信息字典
            
        Returns:
            对应的图标字符
        """
        detail_type = detail_info.get("type", "")
        
        # 根据任务类型返回图标
        if task_type == "category":
            return "▪"
        
        elif task_type == "template":
            if detail_info.get("level") == 2:  # 模板根节点
                return "▸"
            # 根据详情类型前缀匹配
            for prefix, icon in cls.TEMPLATE_ICONS.items():
                if detail_type.startswith(prefix):
                    return icon
            return cls.TEMPLATE_ICONS["default"]
        
        elif task_type == "instance":
            if detail_info.get("level") == 2:  # 实例根节点
                return "▸"
            # 根据详情类型前缀匹配
            for prefix, icon in cls.INSTANCE_ICONS.items():
                if detail_type.startswith(prefix):
                    return icon
            return cls.INSTANCE_ICONS["default"]
        
        elif task_type == "combat":
            # 根据详情类型中的关键词匹配
            for keyword, icon in cls.COMBAT_ICONS.items():
                if keyword in detail_type:
                    return icon
            return cls.COMBAT_ICONS["default"]
        
        elif task_type == "management":
            # 根据详情类型中的关键词匹配
            for keyword, icon in cls.MANAGEMENT_ICONS.items():
                if keyword in detail_type:
                    return icon
            return cls.MANAGEMENT_ICONS["default"]
        
        # 节点图相关任务
        if detail_type.startswith("graph"):
            # 优先匹配完整类型
            if detail_type in cls.GRAPH_ICONS:
                return cls.GRAPH_ICONS[detail_type]
            # 匹配 connect 关键词
            if "connect" in detail_type:
                return cls.GRAPH_ICONS["graph_connect"]
            return cls.GRAPH_ICONS["default"]
        
        # 复合节点相关任务
        if detail_type.startswith("composite_"):
            return cls.COMPOSITE_ICONS.get(detail_type, cls.COMPOSITE_ICONS["default"])
        
        return "•"


class StepTypeColors:
    """步骤类型与节点类别配色（用于任务清单的白底可读着色）。

    - 统一集中到此，避免在组件内硬编码颜色值
    - 步骤类型优先，其次（针对节点图步骤）尝试按节点类别着色
    """

    # 步骤类型 → 颜色（统一从 ThemeColors 中取值，便于主题统一管理）
    STEP_COLORS = {
        # 图根/事件流容器（深色以示区分）
        "template_graph_root": ThemeColors.TODO_STEP_TEMPLATE_GRAPH_ROOT,
        "event_flow_root": ThemeColors.TODO_STEP_EVENT_FLOW_ROOT,

        # 创建/连线/配置（为每种类型分配更显眼且彼此区分的颜色）
        "graph_create_node": ThemeColors.TODO_STEP_GRAPH_CREATE_NODE,
        "graph_create_and_connect": ThemeColors.TODO_STEP_GRAPH_CREATE_AND_CONNECT,
        "graph_create_and_connect_reverse": ThemeColors.TODO_STEP_GRAPH_CREATE_AND_CONNECT_REVERSE,
        "graph_create_and_connect_data": ThemeColors.TODO_STEP_GRAPH_CREATE_AND_CONNECT_DATA,

        "graph_connect": ThemeColors.TODO_STEP_GRAPH_CONNECT,
        "graph_connect_merged": ThemeColors.TODO_STEP_GRAPH_CONNECT_MERGED,

        "graph_config_node": ThemeColors.TODO_STEP_GRAPH_CONFIG_NODE,
        "graph_config_node_merged": ThemeColors.TODO_STEP_GRAPH_CONFIG_NODE_MERGED,
        "graph_set_port_types_merged": ThemeColors.TODO_STEP_GRAPH_SET_PORT_TYPES_MERGED,

        # 动态端口与分支配置
        "graph_add_variadic_inputs": ThemeColors.TODO_STEP_GRAPH_ADD_VARIADIC_INPUTS,
        "graph_add_dict_pairs": ThemeColors.TODO_STEP_GRAPH_ADD_DICT_PAIRS,
        "graph_add_branch_outputs": ThemeColors.TODO_STEP_GRAPH_ADD_BRANCH_OUTPUTS,
        "graph_config_branch_outputs": ThemeColors.TODO_STEP_GRAPH_CONFIG_BRANCH_OUTPUTS,
        # 信号与结构体相关步骤
        "graph_signals_overview": ThemeColors.TODO_STEP_GRAPH_SIGNALS_OVERVIEW,
        "graph_bind_signal": ThemeColors.TODO_STEP_GRAPH_BIND_SIGNAL,
        "graph_bind_struct": ThemeColors.TODO_STEP_GRAPH_BIND_STRUCT,
    }

    # 节点类别 → 颜色（与图场景标题栏色系一致）
    NODE_CATEGORY_COLORS = {
        # 简称/完整版均支持
        "查询": ThemeColors.NODE_CATEGORY_QUERY,
        "查询节点": ThemeColors.NODE_CATEGORY_QUERY,
        "事件": ThemeColors.NODE_CATEGORY_EVENT,
        "事件节点": ThemeColors.NODE_CATEGORY_EVENT,
        "运算": ThemeColors.NODE_CATEGORY_COMPUTE,
        "运算节点": ThemeColors.NODE_CATEGORY_COMPUTE,
        "执行": ThemeColors.NODE_CATEGORY_EXECUTION,
        "执行节点": ThemeColors.NODE_CATEGORY_EXECUTION,
        "流程控制": ThemeColors.NODE_CATEGORY_FLOW,
        "流程控制节点": ThemeColors.NODE_CATEGORY_FLOW,
        # 复合节点在白底上用次要紫，避免纯白不可读
        "复合": ThemeColors.SECONDARY,
        "复合节点": ThemeColors.SECONDARY,
    }

    @classmethod
    def get_step_color(cls, detail_type: str) -> str:
        if not isinstance(detail_type, str):
            return ThemeColors.TEXT_PRIMARY
        return cls.STEP_COLORS.get(detail_type, ThemeColors.PRIMARY)

    @classmethod
    def get_node_category_color(cls, category: str) -> str:
        return cls.NODE_CATEGORY_COLORS.get(category, "")


class TodoStyles:
    """样式相关常量"""
    
    # 定时器延迟（毫秒）
    STATS_UPDATE_DELAY = 300  # 统计更新防抖延迟
    ANIMATION_DELAY = 1  # 动画启动延迟
    # 预览聚焦动画节流：连续请求间隔小于该值（毫秒）时自动改用瞬间跳转，避免阻塞下一步
    PREVIEW_FOCUS_MIN_INTERVAL_MS = 450
    
    # 布局尺寸
    FOCUS_MARGIN = 100  # 聚焦边距（像素）
    
    # 节点图任务类型（用于右侧预览切换条件）
    GRAPH_TASK_TYPES = [
        "template_graph_root",
        "event_flow_root",
        "graph_create_node",
        "graph_config_node",
        "graph_config_node_merged",
        "graph_set_port_types_merged",
        "graph_connect",
        "graph_connect_merged",
        "graph_create_and_connect",
        "graph_create_and_connect_reverse",
        "graph_create_branch_node",
        # 动态端口添加步骤：点击时同样展示节点图预览（可编辑）
        "graph_add_variadic_inputs",
        "graph_add_dict_pairs",
        "graph_add_branch_outputs",
        "graph_config_branch_outputs",
        # 信号相关步骤
        "graph_signals_overview",
        "graph_bind_signal",
    ]

    # 图相关但仅在详情中展示的步骤类型（不切换到右侧图预览）
    GRAPH_DETAIL_TYPES_WITHOUT_PREVIEW = [
        "graph_variables_table",
    ]

    # 按钮样式（从主题色构建，避免直接写死十六进制）
    @staticmethod
    def execute_button_qss() -> str:
        return (
            f"QPushButton {{"
            f" background-color: {ThemeColors.SUCCESS};"
            f" color: {ThemeColors.TEXT_ON_PRIMARY};"
            " font-size: 14px; font-weight: bold; border: none; border-radius: 5px; padding: 8px;"
            " }"
            f" QPushButton:hover {{ background-color: {ThemeColors.SUCCESS_LIGHT}; }}"
            f" QPushButton:pressed {{ background-color: {ThemeColors.SUCCESS}; }}"
        )

    @staticmethod
    def back_button_qss() -> str:
        return (
            f"QPushButton {{"
            f" background-color: {ThemeColors.BORDER_DARK};"
            f" color: {ThemeColors.TEXT_ON_PRIMARY};"
            " font-size: 12px; border: none; border-radius: 5px; padding: 6px 12px;"
            " }"
            f" QPushButton:hover {{ background-color: {ThemeColors.BORDER_NORMAL}; }}"
        )

    @staticmethod
    def widget_stylesheet() -> str:
        """任务清单组件整体样式（简化版，依赖全局主题提供大部分外观）。"""
        bg_main = ThemeColors.BG_MAIN
        bg_card = ThemeColors.BG_CARD
        text_primary = ThemeColors.TEXT_PRIMARY

        # 仅保留最基础、语法绝对安全的样式，避免触发 Qt 样式表解析错误。
        return (
            f"TodoListWidget {{ background-color: {bg_main}; }}"
            f"#leftCard {{ background-color: {bg_card}; border: none; }}"
            f"QLabel {{ color: {text_primary}; }}"
        )


@dataclass(frozen=True)
class StepExecutionProfile:
    """执行相关能力标签的汇总结果。

    统一描述某个 detail_type 是否属于图根 / 事件流根 / 复合步骤 / 叶子图步骤，
    以及是否可执行、是否支持“执行剩余步骤”等能力。
    """

    detail_type: str
    is_template_graph_root: bool
    is_event_flow_root: bool
    is_composite_step: bool
    is_leaf_graph_step: bool
    # 额外能力标签：供 UI 侧统一读取，避免在各组件内重复计算
    supports_preview: bool
    supports_auto_check: bool
    supports_context_menu_execution: bool

    @property
    def is_executable(self) -> bool:
        """是否可以通过执行入口触发执行。"""
        return (
            self.is_template_graph_root
            or self.is_event_flow_root
            or self.is_composite_step
            or self.is_leaf_graph_step
        )

    @property
    def supports_execute_remaining(self) -> bool:
        """是否支持“从当前步骤 / 事件流起执行剩余序列”功能。"""
        return self.is_leaf_graph_step or self.is_event_flow_root


class StepTypeRules:
    """detail_type / 步骤类型语义判断的集中入口。

    - 统一判断“图根 / 事件流根 / 叶子图步骤 / 复合步骤”等语义标签
    - 统一维护“可预览 / 可自动勾选 / 支持富文本 token / 支持右键执行”的类型集合
    - UI 侧其它模块应尽量依赖这里的判断，而不是在各自组件内硬编码字符串集合
    """

    # 图根 / 事件流根
    GRAPH_ROOT_TYPES = ("template_graph_root", "event_flow_root")

    # 自动勾选的叶子步骤类型（仅针对图相关的实际操作步骤）
    AUTO_CHECK_GRAPH_STEP_TYPES = {
        "graph_create_node",
        "graph_create_and_connect",
        "graph_create_and_connect_reverse",
        "graph_create_and_connect_data",
        "graph_create_branch_node",
        "graph_connect",
        "graph_connect_merged",
        "graph_config_node",
        "graph_config_node_merged",
        "graph_set_port_types_merged",
        "graph_add_variadic_inputs",
        "graph_add_dict_pairs",
        "graph_add_branch_outputs",
        "graph_config_branch_outputs",
        "graph_signals_overview",
        "graph_bind_signal",
        "graph_bind_struct",
    }

    # 支持在任务树上渲染富文本 token 的图步骤类型
    RICH_TEXT_GRAPH_STEP_TYPES = {
        "graph_connect",
        "graph_connect_merged",
        "graph_create_node",
        "graph_create_and_connect",
        "graph_create_and_connect_reverse",
        "graph_create_and_connect_data",
        # 配置 / 类型设置
        "graph_set_port_types_merged",
        "graph_config_node_merged",
        # 动态端口与分支配置
        "graph_add_branch_outputs",
        "graph_config_branch_outputs",
        "graph_add_variadic_inputs",
        "graph_add_dict_pairs",
        # 信号相关
        "graph_bind_signal",
    }

    # 支持右键菜单“仅执行此步骤”的类型集合
    CONTEXT_MENU_EXECUTABLE_STEP_TYPES = {
        "graph_create_node",
        "graph_connect",
        "graph_connect_merged",
        "graph_create_and_connect",
        "graph_set_port_types_merged",
        "graph_config_node_merged",
        "graph_add_variadic_inputs",
        "graph_add_dict_pairs",
        "graph_add_branch_outputs",
        "graph_config_branch_outputs",
    }

    # 配置类步骤（节点参数配置相关）
    CONFIG_STEP_TYPES = {
        "graph_config_node",
        "graph_config_node_merged",
    }

    # 类型设置类步骤（端口类型、分支类型等）
    TYPE_SETTING_STEP_TYPES = {
        "graph_set_port_types_merged",
    }

    @classmethod
    def _normalize_detail_type(cls, detail_type: object) -> str:
        if isinstance(detail_type, str):
            return detail_type
        if detail_type is None:
            return ""
        return str(detail_type)

    # === 基础分类 ===

    @classmethod
    def is_template_graph_root(cls, detail_type: object) -> bool:
        return cls._normalize_detail_type(detail_type) == "template_graph_root"

    @classmethod
    def is_event_flow_root(cls, detail_type: object) -> bool:
        return cls._normalize_detail_type(detail_type) == "event_flow_root"

    @classmethod
    def is_graph_root(cls, detail_type: object) -> bool:
        normalized = cls._normalize_detail_type(detail_type)
        return normalized in cls.GRAPH_ROOT_TYPES

    @classmethod
    def is_composite_step(cls, detail_type: object) -> bool:
        normalized = cls._normalize_detail_type(detail_type)
        return normalized.startswith("composite_")

    @classmethod
    def is_graph_step(cls, detail_type: object) -> bool:
        """是否属于“图相关步骤”（含图根 / 事件流根 / 叶子图步骤 / 图内汇总步骤等）。"""
        normalized = cls._normalize_detail_type(detail_type)
        if not normalized:
            return False
        if normalized in cls.GRAPH_ROOT_TYPES:
            return True
        if normalized.startswith("graph"):
            return True
        graph_task_types = getattr(TodoStyles, "GRAPH_TASK_TYPES", ())
        return normalized in graph_task_types

    @classmethod
    def is_leaf_graph_step(cls, detail_type: object) -> bool:
        """是否为可执行的“叶子图步骤”（排除图根 / 事件流根 / 仅详情步骤）。"""
        normalized = cls._normalize_detail_type(detail_type)
        if not cls.is_graph_step(normalized):
            return False
        if normalized in cls.GRAPH_ROOT_TYPES:
            return False
        no_preview_types = getattr(TodoStyles, "GRAPH_DETAIL_TYPES_WITHOUT_PREVIEW", ())
        if normalized in no_preview_types:
            return False
        return True

    @classmethod
    def is_config_step(cls, detail_type: object) -> bool:
        """是否为“配置节点参数”的步骤。"""
        normalized = cls._normalize_detail_type(detail_type)
        return normalized in cls.CONFIG_STEP_TYPES

    @classmethod
    def is_type_setting_step(cls, detail_type: object) -> bool:
        """是否为“设置端口/分支类型”的步骤。"""
        normalized = cls._normalize_detail_type(detail_type)
        return normalized in cls.TYPE_SETTING_STEP_TYPES

    @classmethod
    def is_preview_only_step(cls, detail_type: object) -> bool:
        """是否为仅在详情中展示、不切换到图预览的步骤。"""
        normalized = cls._normalize_detail_type(detail_type)
        no_preview_types = getattr(TodoStyles, "GRAPH_DETAIL_TYPES_WITHOUT_PREVIEW", ())
        return normalized in no_preview_types

    @classmethod
    def should_have_virtual_detail_children(cls, detail_type: object) -> bool:
        """是否应在树中为该步骤附加虚拟“明细子项”。

        目前仅用于：
        - 合并参数配置：graph_config_node_merged
        - 多分支分支输出配置：graph_config_branch_outputs
        - 合并端口类型设置：graph_set_port_types_merged
        """
        normalized = cls._normalize_detail_type(detail_type)
        if cls.is_type_setting_step(normalized):
            return True
        return normalized in ("graph_config_node_merged", "graph_config_branch_outputs")

    # === 能力标签 ===

    @classmethod
    def should_preview_graph(cls, detail_type: object) -> bool:
        """是否应切换到右侧图预览（图根 / 图内操作步骤）。"""
        normalized = cls._normalize_detail_type(detail_type)
        if not cls.is_graph_step(normalized):
            return False
        no_preview_types = getattr(TodoStyles, "GRAPH_DETAIL_TYPES_WITHOUT_PREVIEW", ())
        return normalized not in no_preview_types

    @classmethod
    def is_auto_checkable_step(cls, detail_type: object) -> bool:
        normalized = cls._normalize_detail_type(detail_type)
        return normalized in cls.AUTO_CHECK_GRAPH_STEP_TYPES

    @classmethod
    def supports_rich_tokens(cls, detail_type: object) -> bool:
        normalized = cls._normalize_detail_type(detail_type)
        return normalized in cls.RICH_TEXT_GRAPH_STEP_TYPES

    @classmethod
    def supports_context_menu_execution(cls, detail_type: object) -> bool:
        normalized = cls._normalize_detail_type(detail_type)
        return normalized in cls.CONTEXT_MENU_EXECUTABLE_STEP_TYPES

    # === 复合能力视图 ===

    @classmethod
    def build_execution_profile(cls, detail_type: object) -> StepExecutionProfile:
        """构建给定 detail_type 的执行能力画像。

        供 UI 层统一判断“是否可执行/是否图根/是否事件流根/是否复合/是否叶子图步骤”等场景使用，
        避免在多个组件中重复计算这些布尔标记。
        """
        normalized = cls._normalize_detail_type(detail_type)
        is_template_graph_root = cls.is_template_graph_root(normalized)
        is_event_flow_root = cls.is_event_flow_root(normalized)
        is_composite_step = cls.is_composite_step(normalized)
        is_leaf_graph_step = cls.is_leaf_graph_step(normalized)
        supports_preview = cls.should_preview_graph(normalized)
        supports_auto_check = cls.is_auto_checkable_step(normalized)
        supports_context_menu_execution = cls.supports_context_menu_execution(normalized)
        return StepExecutionProfile(
            detail_type=normalized,
            is_template_graph_root=is_template_graph_root,
            is_event_flow_root=is_event_flow_root,
            is_composite_step=is_composite_step,
            is_leaf_graph_step=is_leaf_graph_step,
            supports_preview=supports_preview,
            supports_auto_check=supports_auto_check,
            supports_context_menu_execution=supports_context_menu_execution,
        )


class PortConstants:
    """端口相关常量"""
    
    # 流程端口名称集合
    FLOW_PORTS = {
        '流程入', '流程出', 
        '是', '否', '默认', 
        '循环体', '循环完成', '跳出循环'
    }


class LayoutConstants:
    """布局常量"""
    
    # 分割器默认尺寸
    # 任务清单左栏默认略宽（但可拖到更宽），最小宽度仍以 ThemeSizes.LEFT_PANEL_WIDTH 保底
    # 默认额外宽度相对早期版本缩小约 1/3，给中部详情/预览区域留出更多空间
    SPLITTER_LEFT_WIDTH = ThemeSizes.LEFT_PANEL_WIDTH + 100   # 左侧任务清单默认宽度（适度收窄）
    SPLITTER_RIGHT_WIDTH = 320  # 右侧详情面板宽度（适度放大）
    
    # 分割器权重
    SPLITTER_LEFT_STRETCH = 1
    SPLITTER_RIGHT_STRETCH = 3
    
    # 树形控件缩进
    TREE_INDENTATION = 20
    
    # 详情面板最小高度
    DETAIL_TEXT_MIN_HEIGHT = 200
    
    # 预览视图最小高度
    PREVIEW_VIEW_MIN_HEIGHT = 400


class CombatTypeNames:
    """战斗类型名称映射"""
    
    NAMES = {
        "combat_player_template": "玩家模板",
        "combat_player_class": "职业",
        "combat_skill": "技能",
        "combat_unit_status": "单位状态",
        "combat_projectile": "投射物",
        "combat_item": "道具",
    }
    
    @classmethod
    def get_name(cls, combat_type: str) -> str:
        """获取战斗类型名称"""
        return cls.NAMES.get(combat_type, "战斗配置")


class ManagementTypeNames:
    """管理类型名称映射"""
    
    NAMES = {
        "management_timer": "计时器",
        "management_variable": "全局变量",
        "management_preset_point": "预设点"
    }
    
    @classmethod
    def get_name(cls, mgmt_type: str) -> str:
        """获取管理类型名称"""
        return cls.NAMES.get(mgmt_type, "管理配置")

