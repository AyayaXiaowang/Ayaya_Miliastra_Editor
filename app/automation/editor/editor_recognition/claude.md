## 目录用途
- 编辑器节点识别与视口映射：基于截图/OCR/模板匹配，回答“哪些节点可见/位置在哪”，并建立 program↔editor 坐标映射供后续点击/拖拽使用。
- 作为 `EditorExecutor` 的识别/几何核心层：不直接做键鼠输入，不直接依赖 UI；只消费 `app.automation.capture` 提供的截图与识别原语。

## 当前状态
- `recognition.py`：对外 facade/兼容层，保留主要 API（如 `recognize_visible_nodes()`、`verify_and_update_view_mapping_by_recognition()`、`synchronize_visible_nodes_positions()` 等）；内部逻辑已拆分到更小模块避免单文件膨胀。
- `constants.py`：识别/拟合相关阈值与策略常量（容差、策略标识等）。
- `models.py`：识别/拟合数据结构（映射对、拟合结果等）。
- `fallbacks.py`：兜底策略（例如唯一标题比例对齐、锚点降级匹配）。
- `mappings.py`：构建“模型节点 ↔ 检测节点”配对的数据准备。
- `logging_utils.py`：识别快照与统计日志输出。
- 其余 `view_mapping_*.py` / `visible_nodes.py` / `position_sync.py` 等模块分别承载视口拟合、可见节点识别与位置同步等子职责。

## 注意事项
- **纯职责**：保持识别与几何逻辑的纯函数风格；不要在此层做输入操作或与 UI 直接耦合。必要副作用仅通过执行器状态字段、日志或可视化回调体现。
- **坐标锚点语义**：所有“节点位置”几何运算统一以节点 bbox **左上角**为锚点；`GraphModel.nodes[*].pos` 也被视为左上角坐标。需要中心点时在调用侧显式计算，不要改变锚点语义。
- **调用前置**：坐标换算依赖执行器的 `scale_ratio` 与 `origin_node_pos`；调用前需确保已完成缩放检查与视口校准。
- **调试落盘**：如需输出调试快照，应写入运行时缓存根目录下的 `debug/` 子目录，并通过统一的缓存/写盘服务完成（避免在本包内手写路径与 JSON 写入）。
