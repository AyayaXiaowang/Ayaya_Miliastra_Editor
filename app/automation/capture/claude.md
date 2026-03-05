## 目录用途
编辑器窗口捕获子包：提供 DPI 感知、截图、ROI 裁剪、OCR、模板匹配、鼠标操作等基础能力，并向执行/监控模块输出可视化叠加与日志。

## 当前状态
- 典型模块：`dpi_awareness.py`（DPI）、`screen_capture.py`（截图）、`roi_config.py`/`roi_constraints.py`（ROI 与裁剪）、`ocr.py`（OCR）、`template_matcher.py`（模板匹配）、`mouse_ops.py`（点击/拖拽）、`cache.py`（LRU 缓存）、`emitters.py`/`overlay_helpers.py`（监控输出与叠加层辅助）。
- 对外统一入口为 `app.automation.capture`（`capture/__init__.py` 重新导出公共接口），保持调用侧导入稳定。
- OCR 依赖采用惰性加载：未使用 OCR 时不强绑定本地推理环境。

## 注意事项
- 所有截图相关调用需确保 DPI 感知只初始化一次，并以物理像素坐标工作，避免缩放环境下坐标漂移。
- “强制节点图 ROI”应使用成对开关或上下文管理器，避免全局状态残留影响后续识别。
- 缓存键应基于像素内容哈希，避免因 DPI/颜色空间差异产生误命中或漏命中。
- 鼠标操作需支持输入阻止保护；中文字体路径如需自定义，通过环境变量 `GRAPH_GENERATER_CHINESE_FONT_PATH` 指定。

