## 目录用途
存放与高级概念、编辑器特化功能相关的扩展配置数据类与模型，例如额外高级配置、总览配置等。这里的模块主要负责描述配置结构与序列化方式，不直接耦合具体运行时逻辑。

## 当前状态
- 以 `dataclass` 为主，聚焦数据建模与导出。
- 被编辑器、校验器与工具脚本作为纯配置依赖使用。

## 注意事项
- 避免在代码中硬编码外部文档的具体存储路径或网址，仅保留必要的语义性说明。
- 如需引用设计资料，请使用抽象描述（如“内部设计文档”“内部配置规范”），不要暴露知识库或文档系统的目录结构。
- 模块内的“参考路径/导入路径”说明统一使用 `engine.configs.*` 的真实模块路径，避免出现过时命名造成检索与导航混乱。

# Specialized 配置

## 目录用途
专业化与高级配置集合，包含仇恨系统、战斗设置、UI控件、能力单元、节点图、游戏系统等。

## 关键文件

### 核心专业化配置
- `specialized_configs.py`: 属性增长、仇恨系统、受击盒、战斗设置
- `hitbox_configs.py`: 受击盒详细配置
- `creature_settings_configs.py`: 造物常规设置（游荡、战斗检测、脱战、领地、技能）
- `combat_effect_configs.py`: 战斗特效与战斗设置
- `ability_units_configs.py`: 能力单元系统（攻击盒、目标筛选、攻击参数、表现效果）

### UI 控件配置
- `ui_widget_configs.py`: **权威定义** - 所有UI控件（交互按钮、卡牌选择器、弹窗、文本框、计分板、计时器、进度条）
  - 进度条颜色调色板在该文件内集中维护为单一真相源（五色 hex，并与真源 `.gil` 的 `color_code` 0..4 对齐），供 UI 面板与工具脚本复用，避免口径漂移；颜色仅允许五色，不做旧值兼容或近似映射。

### 扩展配置系统
- `deployment_configs.py`: 实体布设组、数据复制粘贴
- `node_graph_configs.py`: 节点图核心、通用功能、调试、结构体（基础结构体与局内存档结构体定义）；结构体字段允许类型集合统一由 `engine/type_registry.py` 提供，避免与验证/端口/UI 出现漂移
- `struct_definitions_data.py`: 结构体定义访问接口（提供 `list_struct_ids` / `get_struct_payload` 等函数）。支持注入当前 `ResourceManager` 以按“共享根 + 当前存档根”作用域过滤结构体列表；未注入时回退为全库 Schema 聚合视图（适用于校验/诊断等全局场景）。
- `signal_definitions_data.py`: 基于代码资源 Schema 视图封装的信号定义访问接口（提供 `list_signal_ids` / `get_signal_payload` 等函数，数据来源于 `engine.resources.definition_schema_view` 聚合的代码级信号定义：`assets/资源库/共享/管理配置/信号/**.py` + `assets/资源库/项目存档/<package_id>/管理配置/信号/**.py`）
- `game_systems_configs.py`: 技能资源、聊天系统、成就、排行榜、竞技段位
- `creature_info_configs.py`: 单位状态效果、造物技能、行为模式
- `resource_system_extended_configs.py`: 商店/背包/道具/装备/货币模板（编辑器级）

### 高级编辑器配置
- `advanced_configs.py`: 高级配置（单位状态、关卡结算、堆叠规则等）
- `additional_advanced_configs.py`: UI控件组、布局、技能动画、特效资产、编辑器设置，以及编辑器界面与知识库文档（doc_reference）的映射；当前以单文件集中管理，后续如需可按主题拆分
- `overview_configs.py`: 全局概览配置

## 面向开发者的要点

### 导入推荐
```python
# ✅ 推荐：按需导入
from engine.configs.specialized.game_systems_configs import AchievementConfig
from engine.configs.specialized import ui_widget_configs
from engine.configs.specialized import resource_system_extended_configs

# ⚠️  避免：通配导入（命名冲突风险）
from engine.configs.specialized import *
```

### 权威定义位置
- **UI 控件**: `ui_widget_configs.py`（唯一权威）
- **能力单元**: `ability_units_configs.py`（唯一权威）
- **节点图**: `node_graph_configs.py`（核心）+ `specialized_configs.py`（部分）
- **游戏系统**: `game_systems_configs.py`（成就/排行榜/聊天等）
- **资源系统模板**: `resource_system_extended_configs.py`（编辑器级）vs `combat.resource_system_configs`（运行时）

### 重复定义说明
本包与其他包存在部分同名类，已通过以下方式消歧：
1. **UI 控件**：权威定义在 `ui_widget_configs.py`，其他地方仅导入
2. **能力单元**：权威定义在 `ability_units_configs.py`，其他地方仅导入
3. **战斗设置**：`CombatSettingsConfig` 在多处有不同版本（specialized, combat），按领域选择
4. **资源系统**：模板配置（specialized）vs 运行时配置（combat, management）

## 注意事项与边界条件
- 扩展配置系统已按专题拆分为多个模块（deployment/node_graph/game_systems/creature_info/resource_system_extended 等），不再提供 `extended_configs.py` 聚合入口，导入时请直接引用相应模块
- `additional_advanced_configs.py` 是体量较大的综合配置文件，当前结构按 UI/编辑器/动画/特效等主题划分字段，后续可按需要拆分到独立模块
- **同名类消歧**：通过 `__init__.py` 中的专用别名导出（如 `SpecializedPopupConfig`、`UIWidgetTimerConfig` 等），避免再提供面向旧文件名的额外类名别名；UI 控件组与布局仅通过 `SimpleWidgetGroupConfig` / `SimpleUILayoutConfig` 暴露简化版配置。
- **跨域调用**：specialized 包内的配置可能被 combat, management, components 引用，修改需考虑影响面

## 当前状态
稳定。已完成核心特化配置定义（仇恨系统、战斗属性、受击盒等）。

### 下一步建议
- 如需进一步细化结构，可考虑将 `additional_advanced_configs.py` 拆分为：
  - `editor_ui_configs.py`: UI控件组、布局
  - `editor_level_configs.py`: 关卡设置、沙盒界面、地形编辑
  - `editor_animation_configs.py`: 技能动画、特效资产、预设状态
  - `editor_testing_configs.py`: 多人/单人测试、资产导入导出
- 统一序列化/反序列化模式（减少样板代码）
- 在 CI 中集成“重复配置类名检查”（避免同名配置类导致导入/反射歧义）

---
注意：本文件不记录任何修改历史。请始终保持对"目录用途、当前状态、注意事项"的实时描述。
