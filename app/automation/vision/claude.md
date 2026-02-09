## 目录用途
- 统一封装自动化层使用的视觉识别能力（节点/端口检测、OCR 标题抽取与映射、一步式整屏识别缓存等）。
- 对上层（执行器、工具脚本、UI 调试入口）暴露稳定的 `app.automation.vision` 门面 API，内部委托给 `vision_backend` 与 `node_detection` 等具体实现。

## 当前状态
- `__init__.py`：视觉门面（Facade），提供节点列表、端口列表、缓存失效、标题映射日志、相位相关位移估计、以及窗口 ROI 内的一步式识别（`recognize_nodes_with_ports_in_window_region`）等高层 API，并对外隐藏底层实现细节。节点列表返回前会做一次“根源层去重”（避免重复 bbox 影响上层匹配），其阈值由 `ui_profile_params` 提供以适配不同分辨率/Windows 缩放。
- `vision_backend.py`：核心视觉识别后端，实现截图区域裁剪、OCR 标题提取与近似映射、节点/端口坐标转换与缓存管理等逻辑；除整屏（节点图区域）缓存识别外，也支持对窗口指定 ROI 执行一步式识别并返回节点+端口（坐标回写到窗口坐标系），用于创建验收与快照预热等“目标位置已知”的场景。模板目录通过 profile 解析器自动选择（避免硬编码 `4K-CN`）。调用一步式识别时对端口模板使用约 0.8 的基础置信度阈值，并在底层识别器中对部分流程端口模板（如 Process 系列）使用不高于 70% 的匹配阈值、对部分泛型数据端口模板（如 Generic 系列）使用不高于 75% 的匹配阈值，以在保持整体精度的前提下提高关键端口的识别召回率。一步式识别的 NMS/同行去重/飞线过滤等阈值由 `ui_profile_params` 推导并注入到识别器（避免散落 magic number）。相位相关位移估计会基于 OpenCV `response` 做可信度过滤，低响应时返回 (0,0) 交由上层回退逻辑处理，避免坐标映射漂移。标题近似映射在判定“是否唯一可回退”时会对候选完整名做去重，避免 client/server 同名重复注册导致误判为多解而放弃纠错。端口识别结果中的 `name_cn` **不在视觉层按节点中文名反查**；端口序号→端口名映射由上层在已解析 `node_def`（唯一）后完成（见 `app.automation.editor.node_snapshot`）。
  - `NodeDetected`（节点检测结果数据结构）在本模块内定义，并作为 `list_nodes` 的稳定返回类型使用。
- `scene_recognizer/`：一步式整屏识别实现（节点矩形/标题/OCR/端口模板命中），包含 `SceneRecognizerTuning` 与模板匹配调试明细（`TemplateMatchDebugInfo`），供 `vision_backend` 复用。
- `ui_profile_params.py`：基于"实际显示设置（分辨率宽度档位 + Windows 缩放）"推导"分辨率/缩放敏感的像素参数"（端口标题栏排除高度、候选列表裁剪参数、缩放 ROI 尺寸、节点几何基准、节点去重阈值、一步式识别调参等），并保留当前选择的 OCR 模板 profile 名用于调试；避免各处散落硬编码。端口标题栏排除高度会根据分辨率档位和缩放比例计算，端口识别使用的最终值会夹取到 **[20px, 26px]**（4K125 实测 26px；所有分辨率都不应超过此上限，且不应低于 20px 以避免排除区域过小）。该模块支持通过 `profile_name_override` 在离线回归/工具脚本中显式指定 profile，避免与本机显示设置耦合。
- `ui_profile_params.py` 在未注册默认 workspace 时会统一委托 `engine.utils.workspace.infer_workspace_root_or_none` 从当前文件向上推断工作区根目录（支持源码仓库与便携版），用于解析 profile，保证 UI 调试入口与识别后端对同一台机器的显示设置使用一致参数。
- 端口模板匹配会跳过节点顶部标题栏区域：优先使用一步式识别在色块检测阶段为**每个节点**测得的 `header_height_px`（动态值），仅在缺失时回退到 `ui_profile_params.get_port_header_height_px` 的 profile 推导值；门面额外提供 `get_node_header_height_px_for_bbox(image, bbox)` 便于上层（如 OCR 文本定位）复用该动态高度做顶部排除。
- `ocr_utils.py`：OCR 引擎获取与中文文本抽取工具函数，统一封装 RapidOCR 使用方式。
- `node_detection.py`：基于模板匹配/色块检测等能力的节点与端口检测辅助逻辑。
- `ocr_template_profile.py`：OCR 模板 profile 扫描与自动选择（按屏幕宽度档位 + Windows 缩放 + 语言），并提供“profile 不匹配时”的提示文案；支持通过环境变量 `GRAPH_GENERATER_OCR_TEMPLATE_PROFILE` 强制指定 profile。

## 注意事项
- 所有运行时代码与 CLI 工具如需调用视觉识别能力，应通过 `app.automation.vision` 入口导入，不直接依赖历史路径或内部调试脚本。
- 窗口客户区截图等能力位于 `app.automation.capture`；`app.automation.vision` 仅在需要时做薄转发，避免在视觉门面中引入额外耦合。
- 模块内不做异常吞没，错误应直接抛出交由调用方或全局异常钩子处理。
- 避免在此处硬编码具体工作区路径或外部资源位置；OCR 模板路径统一通过 profile 解析与工作区解析得到。
- 与分辨率/缩放强相关的像素常量（含端口标题栏高度、候选列表裁剪等）应优先向“profile/配置驱动”演进；当前风险点清单见 `docs/diagnostics/自动化识别_写死像素区域清单.md`。


