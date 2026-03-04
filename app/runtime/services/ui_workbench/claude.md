## 目录用途
`app/runtime/services/ui_workbench/` 存放 **无 PyQt6 依赖** 的 UI Workbench（Web 工作台）领域逻辑与小工具，用于承载“UI 源码浏览/缓存/导入”等可测试能力，供：
- 内置 Workbench（`app.ui.workbench.*`）
- 私有扩展 Workbench 后端（如存在）

复用与下沉，避免 UI 层胶水文件膨胀。

## 当前状态
- `utils.py`：base64/crc32/json 读写、HTML 文件枚举等无副作用小工具。
- `types.py`：导入结果的数据结构（ImportResult/ImportBundleResult）。
- `naming.py`：唯一 ID / 唯一名称 / 名称集合提取的小工具（无副作用）。
- `base_gil_cache.py`：UI Workbench 基底 GIL 的运行期缓存读写（落在 `app/runtime/cache/ui_workbench/`）。
- `ui_source_api.py`：UI源码（HTML）目录与文件读取的纯逻辑（路径解析/目录穿越防护、项目/共享 scope）。
- `ui_catalog_api.py`：从 `management.ui_layouts/ui_widget_templates` 生成 UI 布局/模板清单与详情 payload。
- `ui_import_api.py`：HTML 导入布局的领域逻辑（模板重写、按钮打组、bundle 导入）；**只写入 management，不负责 PackageController 保存链路**。
- `variable_defaults.py`：UI 变量默认值的类型推断与写回辅助（lv/ps）；写盘目标为 `自定义变量注册表.py`（不再生成 `UI_*_网页默认值.py`）。

## 注意事项
- 本目录 **禁止导入 PyQt6 / app.ui**，保持可单测与依赖边界清晰。
- 允许触盘的函数必须是显式调用（禁止在 import 阶段读写磁盘）。
- 错误不兜底：保持 fail-fast，方便定位问题。

