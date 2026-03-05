## 目录用途
`ui/foundation/` 存放与具体业务无关的 UI 基础设施：主题/样式、字体、基础控件、对话框与上下文菜单、导航/Toast、通用交互辅助与快捷键配置等。

## 当前状态
- **主题与样式**：`theme_manager.py` 暴露 `ThemeManager` 与 `Colors/Sizes/Icons/...` token；token 位于 `theme/tokens/`，QSS/HTML 位于 `theme/styles/`。`style_mixins.py` 提供 `apply_panel_style/apply_form_dialog_style/apply_card_style` 等统一入口。
- **字体选择**：`fonts.py` 统一选择 UI/等宽/emoji 字体，并在启动阶段由 `ThemeManager.apply_app_style()` 注入，避免业务组件硬编码字体族名。
- **对话框与输入**：`BaseDialog/FormDialog` 作为通用对话框基类；`dialog_utils.py` 提供标准化的信息/警告/确认/多选对话框。输入弹窗统一从 `app.ui.foundation` 顶层使用 `prompt_text/prompt_item/prompt_int`（实现位于 `input_dialogs.py`）。
- **树/列表与徽章**：`folder_tree_helper.py` 封装目录树构建与展开状态；`shared_resource_badge_delegate.py` 统一“共享”徽章渲染约定。
- **导航与扩展入口**：`navigation_bar.py` 负责左侧模式导航；`NavigationBar.ensure_extension_button(...)` 为私有插件提供稳定的底部扩展按钮注入点。
- **快捷键与 ID**：`keymap_store.py` 管理默认快捷键与用户覆盖（存于运行期缓存）；`id_generator.py` 提供 `generate_prefixed_id()`。
- **交互与提示**：应用级滚轮防误触（禁用 TabBar/SpinBox/未展开 ComboBox 的滚轮变更）；Toast 通知与 `ui_notifier` 提供非阻塞提示（无法解析父窗口时退化为控制台输出）。
- **Windows 专有能力**：`global_hotkey_manager.py` 提供全局热键；`performance_monitor.py` 提供 UI 心跳 + watchdog 采样用于卡顿定位（默认关闭）。

## 注意事项
- 本目录保持“纯 UI 基元”定位：不直接做资源索引/写盘；业务层通过控制器与 `engine.resources` 完成数据访问。
- 统一面向 PyQt6 API；不使用 `try/except` 吞错。
- 需要弹窗/菜单/样式时优先复用本目录入口，避免业务模块直接 new `QMessageBox/QInputDialog` 或散落 QSS。
- Windows 专有能力（如全局热键）使用 ctypes 调用 WinAPI 时必须显式声明 `argtypes/restype`。

 