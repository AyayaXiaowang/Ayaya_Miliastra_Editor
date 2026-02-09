## 目录用途
- 聚合“自动化执行内核”相关模块：执行器协议/实现、步骤分派、坐标映射、视口对齐、可见节点识别等。
- 面向 `app.ui` 与 CLI，对外以 `EditorExecutorProtocol` / `EditorExecutorWithViewport` 作为最小接口契约。

## 当前状态
- **核心入口**
  - `executor_protocol.py`：定义执行器协议与组合协议，供上层仅依赖协议而非实现类。
  - `editor_executor.py`：标准执行器 `EditorExecutor`（入口类），保留初始化与对外 API；启动时会设置 DPI 感知，并自动选择 OCR 模板 profile（如 `4K-100-CN` / `4K-125-CN`），暴露 `executor.ocr_template_profile` 供下游步骤复用；通用能力按 mixin 拆分。
- **EditorExecutor 按职责拆分的 mixin**
  - `editor_executor_view_state.py`：视口 token / 场景快照 / 快速链 / 连线链缓存，以及创建节点后的 ROI 快照预热缓存等状态维护
  - `editor_executor_hooks.py`：等待/输入/右键（暂停/终止钩子）封装
  - `editor_executor_visual.py`：截图 + overlays + 监控面板推送
  - `editor_executor_node_library.py`：节点库懒加载与 NodeDef 解析（含复合节点）；NodeDef 定位统一以 `NodeModel.node_def_ref` 为唯一真源（builtin→canonical key；composite→composite_id），运行时不再允许基于 title/category 的 fallback
  - `editor_executor_debug.py`：创建位置/可见节点/分支歧义等调试入口
- **步骤与算法拆分**
  - `automation_step_types.py`：graph_* 步骤类型与 fast-chain 白名单（纯数据配置，避免跨模块字符串耦合）
  - `editor_exec_steps.py`：单步编排入口（planner → step runner → recognizer → handler），本文件只保留编排骨架与少量通用收尾逻辑
  - `pipeline/`：步骤计划表 / 识别预热 / 视口同步 / 缓存失效 / 回放记录 等横切关注点拆分目录，降低单文件长度与耦合
  - `editor_nodes.py` / `editor_connect.py`：节点创建与连线交互；创建节点后可基于“右键点击点→右下ROI”做局部识别验收并预热节点快照，供后续端口/参数步骤复用以减少整屏识别开销
  - `node_snapshot.py`：场景级快照（GraphSceneSnapshot）与节点端口快照（NodePortsSnapshotCache）；节点端口快照可消费创建阶段预热的 bbox+ports 以跳过一次整屏识别
  - NodePortsSnapshotCache 在拿到端口识别结果后，会通过执行器 `get_node_def_for_model(node)` 取得唯一 `node_def`，再将端口 `(side,index)` 映射为端口名并写入 `PortDetected.name_cn`；该映射严格基于 `node_def_ref` 定位，不再依赖按节点中文名全库反查。
  - `candidate_popup.py`：右键搜索候选列表识别与点击（`Node_list.png` 模板 + OCR）；候选列表模板匹配与弹窗 OCR 使用全窗口范围，并在识别期间临时关闭“强制节点图 ROI”，避免弹窗靠边/超出节点图区域时被裁剪导致漏检。
  - `editor_mapping.py` / `editor_zoom.py` / `editor_recognition/`：坐标映射、缩放控制、视口拟合与可见节点识别
  - `connection_drag.py`：连线拖拽公共封装（可选拖拽后校验回调）

## 注意事项
- 不新增用于吞异常的 `try/except`；故障直接抛出，由上层决定是否重试。
- 跨模块访问执行器只用协议/公开方法，禁止访问形如 `executor._xxx` 的私有成员（建议由开发期静态检查脚本守护）。
- 视口变化（拖拽/缩放/布局变更）后应通过公开接口标记失效，避免复用过期截图/识别缓存。
- OCR 模板资源路径由执行器的 `ocr_template_profile` 统一决定；新增分辨率/缩放支持优先补充 `assets/ocr_templates/<profile>/` 目录，而不是在代码里新增硬编码路径。
- 与分辨率/Windows 缩放强相关的像素参数（如节点几何基准尺寸、位置容差）应统一从 `app.automation.vision.ui_profile_params` 推导；避免在 editor 层继续硬编码 `200x100` 等固定值导致跨分辨率行为漂移。
- 创建节点/搜索弹窗相关等待时间统一由 `ui_constants.py` 管理（例如右键弹窗出现等待、候选点击后稳定等待）；需要适配不同机器性能时优先调整这些常量，避免在流程代码中散落硬编码 `sleep_seconds(...)`。
- 候选列表点击（`candidate_popup.py`）在 OCR 结果中会按 `Node_list.png` 模板命中区域做 X 方向交集过滤：模板命中 X 区间会向右额外扩展 **3×模板宽度**；目标文本框与该 X 区间**无交集则视为无效候选**，用于避免误用来自其他面板/区域的同名 OCR 文本。
- `automation_step_types.py` 作为 graph_* 步骤类型的单一真源：信号/结构体绑定分别使用 `graph_bind_signal` / `graph_bind_struct`，并可参与 fast-chain 以跳过不必要等待（仍保持关键截图与可视化输出）。
- 缩放控件识别（`editor_zoom.py`）的 OCR 区域位于“节点图布置区域”下方的底部栏；执行步骤通常启用“强制节点图 ROI”，因此缩放 OCR 需在局部临时关闭强制 ROI，避免区域被裁剪成空图导致识别失败。
- 连线拖拽可提供“结果校验”（例如拖拽后截图差分确认画面发生变化），但该校验应视为 **best-effort 提示**：真实编辑器侧难以可靠验收连线是否成功，避免因差分误报将已执行的连线步骤标记为失败；需要排查连线异常时应结合端口识别叠加层与回放记录截图定位。
- 连线视口调度（`editor_connect.py`）在节点定位失败触发“同屏对齐”时，会启用 `force_pan_if_inside_margin` 并在仅缺一端时优先对齐缺失端点，避免“目标点落在安全区内→不拖拽”导致视口调度无效。
- 画布吸附（`snap_screen_point_to_canvas_background`）对可见节点 bbox 默认做外扩避让（默认 **14px**，可用执行器属性 `canvas_node_avoid_padding_px` 调整），避免在节点边缘发起右键拖拽/右键点击导致无效或误触。
- 画布吸附提供粗略路径 `snap_screen_point_to_canvas_background_coarse`：仅对当前帧做像素采样寻找允许底色点（不做节点识别/颜色矩形搜索），用于远距离连续拖拽时降低每步开销；粗略吸附失败时由调用方回退到严格吸附。
- 步骤收尾（`editor_exec_steps._click_canvas_blank_after_step`）：
  - **创建节点步骤（graph_create_node / graph_create_and_connect）**：不点击、不吸附；点击候选后节点已在“右键点”落下，直接将鼠标移动回“右键弹出菜单的点击点”，避免额外触发整屏识别与颜色约束日志；
  - **快速链模式 + 连接步骤（graph_connect / graph_connect_merged）**：不点击、不吸附；仅将鼠标移动到“当前步骤关联节点的创建锚点（program→editor 左上角）”，用于移出端口/悬浮态避免遮挡；
  - 其它步骤：仍会执行收尾点击；其中在快速链模式下优先走粗略吸附，避免为了收尾点击反复触发整屏节点识别。
- 视口对齐（`ensure_program_point_visible`）加入“连续拖拽画面无明显变化则中止”的保护，避免在拖拽未生效时按预期位移更新坐标映射造成漂移；并在检测到“拖拽疑似不生效/位移异常”时，后续拖拽切换为**慢拖拽**（默认约 1s）以适配卡顿机器输入节奏。可用执行器属性 `view_pan_no_visual_change_abort_consecutive` / `view_pan_no_visual_change_mean_diff_threshold` 调整阈值，`view_pan_slow_drag_duration_seconds` / `view_pan_slow_drag_steps` 调整慢拖拽参数。
- 视口对齐在远距离多步拖拽场景默认采用“首步相位相关校准 + 后续粗略拖拽更新 + 末端识别校正（必要时重试）”策略，以减少每步识别成本并在末端恢复精度；可用执行器属性 `view_pan_enable_calibrated_steps` / `view_pan_enable_coarse_canvas_snap` / `view_pan_enable_end_recognition_correction` 控制该优化。
- 视口对齐对相位相关（phase correlation）输出增加一致性保护：若估计位移与预期内容位移方向相反或偏差过大，将视为无效并走回退路径，避免 `origin_node_pos` 被一次异常 Δ 拉飞。
- 步骤统一日志（`log_start/log_ok/log_fail`）的 `module_and_function` 字符串统一使用 `app.automation.*` 前缀，避免出现过时命名导致检索与定位困难。
- 锚点校准阶段的“锚点节点出现”轮询默认超时为 **3s**（轮询间隔由 `DEFAULT_WAIT_POLL_INTERVAL_SECONDS` 控制）；若画面不变且未命中，应尽快回退/触发恢复动作，避免无意义长时间等待。
- 端口连线调试叠加层（`port_matching.py`）会额外标注“端口识别跳过的节点顶部区域”（红框），排除高度统一来自 `app.automation.vision.get_port_recognition_header_height_px()`，便于排查分辨率/缩放差异带来的识别偏移问题。

---
本说明仅描述“目录用途 / 当前状态 / 注意事项”，不记录修改历史。
