# 目录用途
- 编辑器窗口捕获模块的子包，集中管理 DPI 感知、截图、OCR、模板匹配、鼠标操作等能力，由 `app.automation.capture` 统一对外暴露

# 当前状态
## 模块划分
- **dpi_awareness.py** - DPI 感知：进程级 DPI 感知设置（Windows Per-Monitor DPI）
- **roi_config.py** - 区域配置：统一定义所有识别区域（ROI - Region of Interest），支持基于比例的常规区域和基于锚点的派生区域；`clip_to_graph_region` / `clip_to_image_bounds` 提供基础裁剪能力；其中 `"节点图缩放区域"` 的派生尺寸会通过 `app.automation.vision.ui_profile_params` 依据 OCR 模板 profile 自动调整，避免不同分辨率/缩放下固定像素失真。
- **roi_constraints.py** - 节点图 ROI 约束：统一封装“强制节点图区域”的裁剪/日志逻辑，供模板匹配与 OCR 共享，内部直接复用 `clip_to_graph_region` 计算交集。
- **cache.py** - 缓存机制：提供 OCR 和模板匹配的 LRU 缓存，基于内容哈希避免重复计算
  - 提供 `enforce_graph_roi_context()` / `disable_graph_roi_context()` 上下文管理器，在“强制节点图 ROI”与“临时关闭强制 ROI”之间安全切换
  - 封装全局状态（`_CaptureState`），提供 `reset_capture_state()` 用于测试隔离
- **screen_capture.py** - 截图功能：窗口/客户区/全屏截图，支持多显示器（all_screens），并提供基于 PrintWindow 的实验性“仅窗口截图”接口；客户区截图复用 `input.win_input.get_client_rect` 统一坐标换算，对外提供 `capture_screen_region` 以绝对坐标直接截取屏幕子区域，避免“全屏抓取再裁剪”的额外成本；所有 `ImageGrab` / PrintWindow 调用前自动执行 `ensure_dpi_awareness_once()`，保证缩放环境下仍以物理像素工作。
- **ocr.py** - OCR 识别：使用 RapidOCR 引擎并结合缓存机制，支持区域限制和结果缓存，并通过 `clip_to_graph_region` 统一节点图裁剪；识别结束后会在 overlays 中附带 `reference_panel` 元数据，供 UI 预览 OCR 文本。RapidOCR/ONNXRuntime 采用惰性加载策略，仅在首次实际调用 OCR 能力时导入，未使用 OCR 时不会额外绑定本地推理环境。
- **color_scanner.py** - 颜色扫描：在截图中查找特定颜色的矩形区域，并提供 `prepare_color_scan_image` 预构建 BGR 像素矩阵，便于多次扫描共用同一份像素数据。
- **template_matcher.py** - 模板匹配：基于 OpenCV 的模板匹配，支持缓存和区域限制，并通过 `reference_panel` 元数据告知 UI 当前模板缩略图，便于监控核对；在完成一次匹配计算时，会将搜索区域和所有高于阈值的候选（含置信度）一并绘制到监控画面上，最终选中的命中框使用高亮颜色标记，便于与其余候选对比；同时提供返回候选中心点和置信度的轻量接口，便于上层结合端口位置选择“距离目标点最近”的命中点。
  - 模板像素 LRU 缓存通过 `cache.create_lru_cache` 复用统一实现，避免维护多套淘汰逻辑
- **mouse_ops.py** - 鼠标操作：点击和拖拽操作，支持 classic/hybrid 模式和输入阻止保护；阻止保护的退出钩子只注册一次，避免在长流程中重复堆栈 atexit 回调；混合点击与拖拽均支持按调用覆写释放后停留时间，便于控制光标复位节奏（快速链模式下跳过缓冲）
  - 拖拽 profile 已统一复用同一套参数，`instant`/`classic` 模式仅切换执行路径，避免配置漂移
- **utils.py** - 工具函数：中文字体加载、文本输入、窗口矩形查询等
- **emitters.py** - 监控输出：统一封装 capture 子模块推送的可视化叠加层与日志
- **overlay_helpers.py** - 叠加层辅助：提供 OCR/文本区域的统一标注构造函数，供 capture 与 core 模块共用，并直接复用 `vision.ocr_utils.normalize_ocr_bbox` 以避免坐标转换重复实现。
- **reference_panels.py** - 参考面板工具：仅依赖 PIL/textwrap，提供 `compose_reference_panel()` 与 `build_reference_panel_payload()`（自动携带模板 PNG 字节），供 capture/core/emitters 在任意层级嵌入视觉参考。

## 统一入口
- 父目录的 `app.automation.capture`（`capture/__init__.py`）作为统一入口，重新导出所有子模块的公共接口，保持向后兼容

## 设计原则
- **单一职责**：每个模块只负责一个明确的功能领域
- **职责清晰**：模块命名直接反映其功能，便于定位和维护
- **向后兼容**：通过 `capture/__init__.py` 的统一导出，现有代码按需 `import capture as editor_capture` 即可继续工作
- **缓存优化**：OCR 和模板匹配基于内容哈希缓存，缓存容量可通过 `engine.configs.settings` 中的 `AUTOMATION_*_CACHE_CAPACITY` 配置项调节，避免在长流程中频繁失效。
- **全局监控**：OCR 和模板匹配自动推送可视化和日志到全局汇聚器

## 依赖关系
```
app.automation.capture (统一入口)
  └─ capture/__init__.py
      ├─ dpi_awareness.py (独立)
      ├─ roi_config.py (独立)
      ├─ cache.py (依赖: roi_config)
      ├─ screen_capture.py (依赖: roi_config)
      ├─ ocr.py (依赖: cache, roi_config, common)
      ├─ color_scanner.py (独立)
      ├─ template_matcher.py (依赖: cache, roi_config, common)
      ├─ mouse_ops.py (依赖: win_input, common, settings)
      └─ utils.py (依赖: common, win_input)
```

# 注意事项
- 所有子模块通过 `capture/__init__.py` 统一导出，外部代码应从 `app.automation.capture`（或按需别名为 `editor_capture`）导入
- 缓存键基于像素内容哈希（包含形状与 dtype），避免 DPI/颜色空间差异造成误命中
- OCR 和模板匹配支持"强制节点图区域"模式：
  - 使用 `set_enforce_graph_roi(True/False)` 手动控制（需配对调用）
  - 推荐使用 `with enforce_graph_roi_context():` 上下文管理器（异常安全，自动恢复）
- `utils.get_chinese_font` 不再写死字体绝对路径：支持通过环境变量 `GRAPH_GENERATER_CHINESE_FONT_PATH` 指定字体文件；未指定时会从系统字体目录探测并回退到 PIL 默认字体。
- 鼠标操作支持输入阻止保护，防止用户干扰自动化执行
- 鼠标操作的经典 / 混合 / 即时配置统一通过 profile 数据驱动，左/右键共享同一实现，修改参数时只需调整字典或设置项
- 所有截图操作支持多显示器（all_screens=True）
- DPI 感知仅在进程级设置一次，避免重复调用
- 全局状态可通过 `reset_capture_state()` 重置，用于测试环境隔离

