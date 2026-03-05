## 目录用途
存放 `tests/` 下的轻量辅助模块（不属于测试用例本身），用于减少测试代码重复并提高路径/夹具等公共逻辑的一致性。

## 当前状态
- `project_paths.py`：提供稳定的仓库根目录定位方法，统一委托 `engine.utils.workspace.resolve_workspace_root` 推断 workspace_root（源码仓库形态即 repo root），避免测试文件移动分组后因手写 `Path(__file__).parents[...]` 规则漂移。
- `ui_preview_mock_server.py`：UI Web 预览页（`ui_app_ui_preview.html`）的 mock `/api/ui_converter/*` 服务器：
  - 用于在不启动主程序的情况下，直接读取 `assets/资源库/项目存档/<package_id>/管理配置/UI源码/` 并驱动预览页运行；
  - 仅实现预览页所需的最小接口（status / ui_source_catalog / ui_source / ui_source_raw），其余接口明确返回“不支持”以避免静默误用。
- `playwright_utils.py`：Playwright 环境探测与跳过策略（chromium 可执行文件缺失时 `pytest.skip`），用于让 UI Web 用例在“仅安装 python 包但未安装浏览器”时保持稳定。

## 注意事项
- 本目录下的模块**不得**以 `test_*.py` 命名，避免被 pytest 误收集。
- 保持无副作用：不要在 import 时修改全局状态（如写文件/启动 UI）。
- 本目录包含 `__init__.py`：用于支持 `tests._helpers.*` 的稳定导入路径（配合 `tests/` 作为 package）。


