## 目录用途
- 存放各类“组件配置”的 **Schema / 枚举 / 数据模型**（以 `dataclass` + `Enum` 为主），供管理配置、校验与运行时做读取/序列化/反序列化。
- 本目录只关心“组件有哪些字段、字段类型与导出结构”，**不承载运行时逻辑或 UI 代码**。

## 当前状态
- **按功能拆分（单一职责）**：
  - `variable_configs.py`：自定义变量组件（含 `VariableDataType`、`CustomVariableComponentConfig` 等）；变量中文类型名口径统一来自 `engine/type_registry.py`（历史 `DICT_ALL` 在规范侧统一映射为 `字典`）。
  - `timer_configs.py`：计时器（含全局计时器/定时器）组件配置。
  - `collision_configs.py`：碰撞/触发相关组件配置。
  - `status_configs.py`：单位状态组件配置。
  - `minimap_configs.py`：小地图标识组件配置。
  - `backpack_configs.py`：背包/装备栏/战利品组件配置。
  - `scan_tag_configs.py`：扫描标签组件配置。
  - `motor_configs.py`：运动器组件配置（投射/跟随/基础/扰动装置等）。
  - `shop_configs.py`：商店组件配置。
  - `effect_configs.py`：特效播放组件配置。
  - `hit_detection_configs.py`：命中检测组件配置。
  - `ui_configs.py`：UI 组件配置（铭牌/气泡等）。
  - `attach_point_configs.py`：挂接点组件配置。
  - `tab_configs.py`：选项卡组件配置（可配置选项卡列表及过滤器挂载信息）。
  - `component_registry.py`：通用组件注册表元数据（名称/说明/适用实体），供规则与 UI 通过统一入口获取组件类型列表与文案。
  - `ui_control_group_model.py`：UI 布局/控件模板/控件配置模型（`UILayout` / `UIControlGroupTemplate` / `UIWidgetConfig`）：
    - 模板支持 `supports_layout_visibility_override`，用于控制“界面布局”中是否允许对该模板做局部显隐覆盖；
    - `extra` 用于保留未知字段，避免仅浏览/轻量编辑时丢失外部生成数据；
    - 反序列化容错：缺少必需字段（如 `template_id`）时会 `warnings.warn` 并返回 `None`，由上层跳过该条目。
    - 进度条预设默认颜色使用统一调色板（`engine.configs.specialized.ui_widget_configs.PROGRESSBAR_COLOR_GREEN_HEX`），避免与 UI 面板/写回工具口径漂移。
  - `__init__.py`：汇总导出，作为对外稳定 API（外部优先从 `engine.configs.components` import）。

## 注意事项
- 字段或枚举变更需同步：管理面板表单/回显、序列化兼容、校验规则口径（避免“文档/实现/数据格式”三方漂移）。
- 避免在此目录硬编码外部文档路径或私有文件名，来源说明保持在“内部设计文档/专题文档”等抽象层级。
- 部分模块间存在轻量依赖（例如 `motor_configs` 依赖 `collision_configs` 的类型）；新增依赖前先确认不会引入循环 import。

---

注意：本文件不记录任何修改历史。请始终保持对“目录用途 / 当前状态 / 注意事项”的实时描述。


