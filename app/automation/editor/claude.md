## 目录用途
- 聚合“自动化执行内核”相关模块：执行器协议/实现、步骤分派、坐标映射、视口对齐、可见节点识别等。
- 面向 `app.ui` 与 CLI，对外以 `EditorExecutorProtocol` / `EditorExecutorWithViewport` 作为最小接口契约。

## 当前状态
- **核心入口**
  - `executor_protocol.py`：定义执行器协议与组合协议，供上层仅依赖协议而非实现类。
  - `editor_executor.py`：标准执行器 `EditorExecutor`（入口类），保留初始化与对外 API；启动时会设置 DPI 感知，并自动选择 OCR 模板 profile（如 `4K-100-CN` / `4K-125-CN`），暴露 `executor.ocr_template_profile` 供下游步骤复用；通用能力按 mixin 拆分。
- **EditorExecutor 按职责拆分的 mixin**
  - `editor_executor_view_state.py`：视口 token / 场景快照 / 快速链 / 连线链缓存等状态维护
  - `editor_executor_hooks.py`：等待/输入/右键（暂停/终止钩子）封装
  - `editor_executor_visual.py`：截图 + overlays + 监控面板推送
  - `editor_executor_node_library.py`：节点库懒加载与 NodeDef 解析（含复合节点）
  - `editor_executor_debug.py`：创建位置/可见节点/分支歧义等调试入口
- **步骤与算法拆分**
  - `automation_step_types.py`：graph_* 步骤类型与 fast-chain 白名单（纯数据配置，避免跨模块字符串耦合）
  - `editor_exec_steps.py`：单步编排入口（planner → step runner → recognizer → handler），本文件只保留编排骨架与少量通用收尾逻辑
  - `pipeline/`：步骤计划表 / 识别预热 / 视口同步 / 缓存失效 / 回放记录 等横切关注点拆分目录，降低单文件长度与耦合
  - `editor_nodes.py` / `editor_connect.py`：节点创建与连线交互
  - `candidate_popup.py`：右键搜索候选列表识别与点击（`Node_list.png` 模板 + OCR）；候选列表模板匹配与弹窗 OCR 使用全窗口范围，并在识别期间临时关闭“强制节点图 ROI”，避免弹窗靠边/超出节点图区域时被裁剪导致漏检。
  - `editor_mapping.py` / `editor_zoom.py` / `editor_recognition/`：坐标映射、缩放控制、视口拟合与可见节点识别
  - `connection_drag.py`：连线拖拽公共封装（可选拖拽后校验回调）

## 注意事项
- 不新增用于吞异常的 `try/except`；故障直接抛出，由上层决定是否重试。
- 跨模块访问执行器只用协议/公开方法，禁止访问形如 `executor._xxx` 的私有成员（配合 `tools/check_executor_private_access.py`）。
- 视口变化（拖拽/缩放/布局变更）后应通过公开接口标记失效，避免复用过期截图/识别缓存。
- OCR 模板资源路径由执行器的 `ocr_template_profile` 统一决定；新增分辨率/缩放支持优先补充 `assets/ocr_templates/<profile>/` 目录，而不是在代码里新增硬编码路径。
- 候选列表点击（`candidate_popup.py`）在 OCR 结果中会按 `Node_list.png` 模板命中区域做 X 方向交集过滤：模板命中 X 区间会向右额外扩展 **3×模板宽度**；目标文本框与该 X 区间**无交集则视为无效候选**，用于避免误用来自其他面板/区域的同名 OCR 文本。
- 缩放控件识别（`editor_zoom.py`）的 OCR 区域位于“节点图布置区域”下方的底部栏；执行步骤通常启用“强制节点图 ROI”，因此缩放 OCR 需在局部临时关闭强制 ROI，避免区域被裁剪成空图导致识别失败。
- 连线拖拽应尽量提供“结果校验”（例如拖拽后截图差分确认画面发生连线变化），避免静默失败导致后续步骤在错误状态上继续执行。
- 画布吸附（`snap_screen_point_to_canvas_background`）对可见节点 bbox 默认做外扩避让（默认 **14px**，可用执行器属性 `canvas_node_avoid_padding_px` 调整），避免在节点边缘发起右键拖拽/右键点击导致无效或误触。
- 视口对齐（`ensure_program_point_visible`）加入“连续拖拽画面无明显变化则中止”的保护，避免在拖拽未生效时按预期位移更新坐标映射造成漂移。可用执行器属性 `view_pan_no_visual_change_abort_consecutive` / `view_pan_no_visual_change_mean_diff_threshold` 调整阈值。
- 视口对齐对相位相关（phase correlation）输出增加一致性保护：若估计位移与预期拖拽内容位移方向相反或偏差过大，将视为无效并走回退路径，避免 `origin_node_pos` 被一次异常 Δ 拉飞。
- 步骤统一日志（`log_start/log_ok/log_fail`）的 `module_and_function` 字符串统一使用 `app.automation.*` 前缀，避免出现过时命名导致检索与定位困难。
- 锚点校准阶段的“锚点节点出现”轮询默认超时为 **3s**（轮询间隔由 `DEFAULT_WAIT_POLL_INTERVAL_SECONDS` 控制）；若画面不变且未命中，应尽快回退/触发恢复动作，避免无意义长时间等待。
- 端口连线调试叠加层（`port_matching.py`）会额外标注“端口识别跳过的节点顶部区域”（红框），排除高度统一来自 `app.automation.vision.get_port_recognition_header_height_px()`，便于排查分辨率/缩放差异带来的识别偏移问题。

---
本说明仅描述“目录用途 / 当前状态 / 注意事项”，不记录修改历史。
