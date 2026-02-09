## 目录用途
- `tests/shape_editor/`：形状编辑器（`private_extensions/shape-editor`）的自动化回归测试。
- 覆盖“项目级持久化”链路：新建空白实体、保存到指定实体（覆盖写入）、默认画布实例保存、实体列表扫描等。

## 当前状态
- 仅包含纯后端测试（不依赖浏览器与 Qt），通过直接调用 `shape_editor_backend.project_persistence` 的函数验证落盘结果。

## 注意事项
- 测试必须使用 `tmp_path` 创建临时资源库目录，禁止读写真实的 `assets/资源库/`，避免污染用户项目存档。
- `target_rel_path` 必须使用 `实体摆放/<file>.json` 形式，且应包含用例覆盖“空字符串（默认画布实例）”与“显式实体文件”两种分支。
