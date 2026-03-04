## 目录用途
`app/automation/editor/`：自动化执行内核（面向真实编辑器）：执行器协议/实现、步骤编排与分派、坐标映射与视口对齐、可见节点/端口快照与缓存等。

## 当前状态
- **协议与实现**：`executor_protocol.py` 定义 `EditorExecutorProtocol` / `ViewportController` 等协议；`editor_executor.py` 提供标准实现 `EditorExecutor` 并按 mixin 拆分视图状态、hooks、可视化、NodeDef 解析与调试能力。
- **步骤编排**：`editor_exec_steps.py` 提供单步编排骨架；横切关注点下沉到 `pipeline/`（计划表、预热、缓存失效、回放记录等）。
- **快照与识别协作**：`node_snapshot.py` 提供场景/节点端口快照缓存，可复用创建阶段的 ROI 预热；`candidate_popup.py` 负责右键候选列表识别与点击；坐标映射/缩放/可见节点识别位于 `editor_mapping.py` / `editor_zoom.py` / `editor_recognition/`。
- **NodeDef 解析**：以 `NodeModel.node_def_ref` 为真源；对 `kind="event"` 采用确定性的 `category/title -> builtin_key` 映射定位 builtin NodeDef（用于端口类型推断/判定），不做 title 猜测式 fallback。

## 注意事项
- 只通过协议/公开方法跨模块访问执行器，禁止调用 `executor._*` 私有实现；视口变化后要显式标记缓存失效，避免复用过期截图/识别结果。
- OCR 模板与分辨率/缩放相关参数统一由 `ocr_template_profile` 与 `app.automation.vision.ui_profile_params` 决定；等待/节奏常量集中在 `ui_constants.py`。
- 不新增 try/except 吞错；故障直接抛出，由上层决定重试/回退。
