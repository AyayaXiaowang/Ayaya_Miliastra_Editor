## 目录用途
- 存放“执行监控面板”的识别测试动作实现（OCR/节点/端口/模板匹配/窗口截图实验等）。

## 当前状态
- `actions_recognition.py`：`RecognitionActions` 的具体实现（大体量逻辑集中于此，供监控面板调用）。
- `__init__.py`：对外只导出 `RecognitionActions`，便于上层保持稳定导入路径。

## 注意事项
- 该目录只承载“测试动作/调试动作”的实现，不直接持有 UI 状态；一律通过回调访问上下文。
- overlays 结构保持 dict，不引入 dataclass，避免连锁改动。
- 不在此处吞异常；错误应直接抛出，便于定位底层识别/截图问题。
- 识别/模板调试能力统一从 `app.automation.vision` / `app.automation.vision.scene_recognizer` 导入，避免引入已移除的外部工具层依赖。



