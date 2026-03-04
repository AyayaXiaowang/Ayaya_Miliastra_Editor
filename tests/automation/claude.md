## 目录用途
存放 automation（自动化执行/协议约束）相关测试，重点回归“协议契约不漂移、跨模块依赖不退回到具体实现类”。

## 当前状态
- `test_executor_protocol_contract.py`：反射级校验 `EditorExecutorProtocol/ViewportController` 的关键方法签名与实现一致，并约束关键模块使用协议类型注解。
- `test_roi_config_bounds.py`：回归自动化截图 ROI 的矩形边界策略：派生 ROI（如“节点图缩放区域”）返回的矩形必须完全落在截图范围内，避免越界与空图。
- `test_port_recognition_header_height_bounds.py`：回归端口识别“标题栏排除高度”的夹取范围，确保 `get_port_header_height_px()` 始终落在约束区间内（含 profile override 参数存在的场景），避免模板误匹配到标题栏。
- `test_enum_dropdown_utils.py`：回归“枚举下拉 OCR 缺字时的顺序推断”与选项文本归一化逻辑（含空白/下划线 `_ / ＿` 的兼容）；并覆盖“OCR 文本无法匹配但识别条目数==枚举总数时的顺序兜底”判定，避免执行阶段在少量漏识别或 UI 展示差异时退化为盲点点击。
- `test_warning_search_region_guard.py`：回归 `search_region` 缺失时 `handle_regular_param_with_warning` 不崩溃，直接返回 False 交由上层走 fallback。
- `test_execute_config_node_merged_regular_param_port_gap_integration.py`：轻量集成回归 `execute_config_node_merged`：普通参数必须走“端口间距法”输入；端口间距法失败应直接失败返回 False；两种情况下都不应调用 `handle_regular_param_fallback`。
- `test_regular_param_port_gap_click.py`：回归“普通参数端口间距法”的几何点击点推导：当上下端口间距 ≥ 1 个端口高度时点击点为 `(+2*w, +1*h)`；间距不足时点击点为 `(+2*w, +0*h)`（偏移基准均为端口中心点）。

## 注意事项
- 测试应尽量避免依赖真实窗口/截图/输入环境；优先做契约级与纯逻辑回归。
- 不使用 `try/except` 吞错，失败直接抛出由 pytest 记录。
- 命令行回归：`python -X utf8 -m pytest -q tests/automation`（也可指定单文件路径）。


