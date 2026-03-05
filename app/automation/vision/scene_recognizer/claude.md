## 目录用途
- 存放“一步式场景识别”实现：在一次图像处理流程中识别节点矩形、标题与端口模板命中，并提供调试用的模板匹配明细。

## 当前状态
- 对外入口集中在 `app.automation.vision.scene_recognizer`：
  - `recognize_scene(...)`：输入节点图画布区域（PIL.Image），输出 `RecognizedNode/RecognizedPort`。
  - `SceneRecognizerTuning`：由 `ui_profile_params` 推导并注入的调参结构（NMS/同行去重/飞线过滤等）。
  - `debug_match_templates_for_rectangle(...)` / `TemplateMatchDebugInfo`：用于 UI“深度端口识别”调试可视化。
- 模块拆分：
  - `models.py`：结果模型与调参 dataclass
  - `io_utils.py`：Windows 中文路径安全的 OpenCV 读写 + debug 输出根目录推导
  - `rectangle_detection.py`：色块/轮廓法检测节点矩形（含 debug_steps 输出）
  - `ocr_titles.py`：标题栏 OCR（拼图式）
  - `template_matching.py`：端口模板匹配 + NMS + 同行去重 + 调试明细
  - `recognize.py`：主流程，组装 nodes/ports，并处理 Settings/Warning 行内规则

## 注意事项
- 模块内不做异常吞没，错误应直接抛出交由调用方处理。
- 本目录只处理传入图像，不负责窗口截图；截图能力在 `app.automation.capture`。
- 与分辨率/缩放强相关的阈值应由上层 profile 注入（见 `ui_profile_params`），避免散落硬编码。
- debug 输出根目录支持环境变量 `GRAPH_GENERATER_DEBUG_OUTPUT_ROOT` 覆写；默认落运行时缓存根目录下的 `debug/one_shot_scene_recognizer/`。


