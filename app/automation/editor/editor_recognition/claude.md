## 目录用途
- 承载编辑器节点识别与视口映射相关的核心逻辑，包括检测结果整理、几何评估以及可见性查询等。
- 为 `editor_executor` 提供基于截图的“节点是否可见 / 在哪里”的统一入口，并负责把识别结果转化为可复用的数据结构。

## 当前状态
- `recognition.py`：**兼容层/薄封装**，保留历史导入路径与对外 API（`recognize_visible_nodes()`、`verify_and_update_view_mapping_by_recognition()`、`synchronize_visible_nodes_positions()` 等），具体实现已拆分到更小模块，避免单文件过大。
- `fallbacks.py` 等辅助模块：封装唯一标题比例对齐、锚点降级匹配等兜底策略，用于在节点文本存在歧义或数量不足时仍尽可能恢复坐标映射。
- 该子包不直接操作键鼠输入，只依赖 `app.automation.capture` 提供的截图与 OCR、模板匹配能力。
 - `visible_nodes.py` 的 `recognize_visible_nodes()` 会在返回结果中附带 `recognized_title`（来自检测到的节点标题），便于 UI 在“定位镜头”等场景展示“识别标题 vs 模型标题”的差异。

## 注意事项
- 保持识别与几何逻辑的纯函数风格，避免在此层做输入操作或与 UI 直接耦合，所有副作用应通过执行器上的状态字段或日志/可视化回调体现。
- 坐标换算依赖执行器的 `scale_ratio` 与 `origin_node_pos`，调用前需确保已通过缩放检查与视口校准获得有效映射。
- 所有与“节点位置”相关的几何运算一律以节点左上角为锚点：检测结果中使用 bbox 左上角作为锚点，`GraphModel.NodeModel.pos` 也被视为左上角坐标；如需几何中心仅用于绘制或点击居中，应在调用侧显式计算，而不要改变锚点语义。
- 当需要记录节点位置变化时，应优先使用偏移量缓存等增量数据结构，避免随意篡改模型层的模板坐标，以保证节点图布局逻辑的一致性。

## editor_recognition 子包

### 目录用途
- 提供节点识别与视口映射更新的高层入口，基于“固定缩放 + 原点平移投票”的方式在程序坐标与编辑器坐标之间建立映射，同时暴露可见节点查询接口。

### 当前状态

- **`__init__.py`**：聚合包的公共 API，对外暴露主要入口函数和数据结构：
  - `prepare_for_connect()`：截图预热
  - `recognize_visible_nodes()`：识别所有可见节点并返回位置信息
  - `is_node_visible_by_id()`：检查单个节点是否可见
  - `verify_and_update_view_mapping_by_recognition()`：通过识别更新视口映射

- **`constants.py`**：集中存放识别/拟合相关的数值与策略常量：
  - 缩放比例容忍度、邻域匹配阈值等
  - 拟合策略标识符：`FIT_STRATEGY_RELATIVE_ANCHORS`（锚点邻域匹配）、`FIT_STRATEGY_ORDINARY_NODES`（普通节点位置匹配）

- **`models.py`**：定义数据结构：
  - `MappingData`：节点映射数据（模型-检测配对）
  - `ViewMappingFitResult`：拟合结果（成功标志、拟合策略）

- **`recognition.py`**：高层入口与可见性检测：
  - 作为兼容层保留函数签名与导出，具体逻辑拆分为：
    - `prewarm.py`：`prepare_for_connect()` 截图预热 + 场景快照注入
    - `view_mapping.py`：`verify_and_update_view_mapping_by_recognition()`（原点投票/相对锚点/单锚点等）
    - `visible_nodes.py`：`recognize_visible_nodes()` / `_find_best_node_bbox()` / `is_node_visible_by_id()`
    - `position_sync.py`：`synchronize_visible_nodes_positions()`（写入偏移缓存）
    - `debug_dump.py`：识别阶段调试落盘（`last_focus_detection.json`），写入运行时缓存根目录下的 `debug/` 子目录（默认 `app/runtime/cache/debug/`）；落盘统一通过 `app.runtime.services.json_cache_service.JsonCacheService`，避免本子包自行拼路径与手写 JSON 写入
    - `view_mapping_*.py`：视口拟合算法细分模块（原点投票、相对锚点、单锚点、普通节点匹配等）

- **`fallbacks.py`**：唯一节点对齐策略实现：
  - `try_unique_ratio_alignment()`：唯一节点比例对齐
  - `collect_unique_titles()`：收集模型与检测中都只有单实例的节点标题

- **`mappings.py`**：配对构建：
  - `build_detection_mappings()`：构建模型节点与检测节点的名称映射，返回 `MappingData` 结构

- **`logging_utils.py`**：识别日志输出：
  - `log_detection_snapshot()`：输出识别快照信息（检测数量、节点列表等）

## 注意事项

- **三阶段识别流程（当前实现）**：
  1. 截图并检测所有节点
  2. 视口映射采用“策略表驱动”：按固定顺序尝试映射策略（原点投票 / 相对锚点 / 唯一比例 / 单锚点），并将“是否允许退化策略”统一收敛为 `allow_degraded_fallback`
  3. 对退化策略建立的映射，会使用普通节点位置匹配进行二次校验（失败则继续下一策略）
  4. 全部失败时提示用户移动视口/扩大镜头
  6. 顶层入口 `verify_and_update_view_mapping_by_recognition(executor, graph_model, ...)` 直接采用上述三阶段匹配流程，不再对外暴露可调的“内点比例 / 最大误差 / 最小内点数”等阈值参数，调参集中在本子包的常量定义中统一管理

- **锚点邻域匹配**：
  - 无需先验校准：以锚点为中心，寻找相邻的若干程序节点及其检测候选，通过 `ΔX/ΔY` 比例一致性确认对应关系
  - 样本越多越稳：至少需命中 2 个邻居；匹配成功后对所有节点执行支持度校验（命中率/偏差）
  - 容差：`compute_position_thresholds(scale)` × `RELATIVE_ANCHOR_TOLERANCE_MULTIPLIER`

- **普通节点位置匹配**：
  - 依赖现有的 `scale_ratio` 和 `origin_node_pos`（通常由锚点推断或唯一节点对齐设定）
  - 计算每个模型节点的预期编辑器坐标：`expected = origin + prog_pos * scale`
  - 与检测框中心对比，偏差在容差内（`compute_position_thresholds() * 1.5`）即算匹配
  - 匹配≥2个节点即认为视口校准成功

- **识别结果缓存**：`verify_and_update_view_mapping_by_recognition()` 成功后会缓存截图与识别结果，`recognize_visible_nodes()` 检测到缓存后直接复用，避免在同一操作内重复识别。缓存使用后立即清除，确保缓存生命周期局限在单次操作内

- **唯一节点比例对齐**：
  - 使用唯一节点集合计算 X/Y 方向的相对距离比例并估算缩放与平移
  - X和Y独立检查，允许 30% 的比例误差
  - 参与节点需≥2个，并通过残差验证（≤48px）

- **调试日志**：系统会输出详细的匹配过程、节点坐标对比、偏差统计等信息，便于诊断匹配失败的根本原因

- 包内模块间通过相对导入（`from .xxx import yyy`）引用，外部模块统一通过 `from . import editor_recognition as _rec` 使用
- 拟合策略通过常量字符串标识，避免魔法值分散
- 所有私有辅助函数统一添加下划线前缀，仅在包内使用

### 典型调用链（概览）

- 视口校准与可见性识别通常按如下顺序调用：
  1. UI 或执行线程通过 `EditorExecutor.ensure_zoom_ratio_50()` 统一外部编辑器缩放；
  2. 调用 `verify_and_update_view_mapping_by_recognition(executor, graph_model, ...)` 完成截图、节点检测与三阶段几何拟合，写入 `scale_ratio` 与 `origin_node_pos`；
  3. 在拟合成功后，通过 `synchronize_visible_nodes_positions(executor, graph_model, ...)` 利用当前识别结果回填一批可见节点的程序坐标，使 `GraphModel.nodes[*].pos` 更贴近真实画面；
  4. 需要查询“当前哪些节点在画面中”时，调用 `recognize_visible_nodes(executor, graph_model)`，得到按 `node_id` 索引的可见性与屏幕坐标映射结果。

- 上述步骤既可以由 UI 场景（如“定位镜头”）驱动，也可以在自动执行线程开始节点图步骤前统一完成一次，以便创建/连线等操作使用与识别一致的坐标系。

