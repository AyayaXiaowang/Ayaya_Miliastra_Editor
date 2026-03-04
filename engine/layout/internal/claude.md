## 目录用途
布局层核心内部实现：`LayoutService`、布局上下文与常量、纯数据图布局算法，以及 `LayoutRegistryContext`（从节点库派生布局所需只读索引与约束）。

## 当前状态
- 本目录集中存放内部实现模块：`layout_service.py`、`layout_context.py`、`layout_algorithm.py`、`data_graph_layout.py`、`layout_models.py`、`constants.py` 等；对外稳定 API 由 `engine.layout` 包级导出。
- `layout_registry_context.py` 提供 `LayoutRegistryContext` 与构建/注入助手：用于在布局阶段显式获得 `workspace_root` 与节点库派生信息，避免任何“按文件位置猜根目录”的隐式回退。
- `LayoutService` 不再通过“端口临时改名/回滚”来修补流程语义；流程口/流程边判定由 `layout/utils` 基于端口类型快照统一收敛，保证动态端口场景可复现且不污染模型。

## 注意事项
- 纯逻辑目录：禁止依赖 `app/*`、`plugins/*`、`assets/*` 或任何 I/O。
- 失败即失败：不使用 `try/except` 吞错或静默回退；缺少 `workspace_root` 等必要信息应直接抛错。
- 影响 UI 绘制基线的常量需与 UI 侧保持一致；以本目录 `constants.py` 为单一真源维护。

