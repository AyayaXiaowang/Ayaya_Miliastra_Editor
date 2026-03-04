# ugc_file_tools/apps 目录说明

## 目录用途
- 存放需要图形界面/交互输入的入口（例如 Tkinter GUI），与纯 CLI 工具脚本分离。

## 当前状态
- 当前包含：`gui_app.py`（Tkinter 简易 GUI；由 `python -m ugc_file_tools gui` 启动）。
  - “一键生成 GIL”面板会调用：`python -m ugc_file_tools.commands.write_graph_generater_package_test2_graphs_to_gil ...`
  - GUI 内对“危险写盘”操作会弹出确认对话框（tool 运行危险工具、以及“一键生成 GIL”）。

## 注意事项
- GUI 内通过 `python -m ugc_file_tools ...` 方式调用子工具时，模块路径必须与实际目录结构一致（工具脚本位于 `ugc_file_tools/commands/`）。
- 路径计算必须使用 `ugc_file_tools.repo_paths`（避免 `Path(__file__).parents[n]` 因目录层级变化而失效）。
- 不使用 `try/except`；错误直接抛出即可。


