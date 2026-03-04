## 目录用途
- 承载任务清单右侧“节点图预览”的控制器与面板：只读加载图、聚焦/高亮动画、以及按步骤类型分发的预览 handler。

## 当前状态
- `TodoPreviewController` 负责聚焦/高亮的公共编排；具体 detail_type 的“选哪些节点/边、怎么组合动作”由 handler 模块分发。
- 预览使用共享画布（GraphView 租约）时，需遵循租约 acquire/release 约束，确保与图编辑器切页时不发生画布归属错乱。

## 注意事项
- handler 只能依赖 controller 的公开 API（无下划线方法）；需要新增能力时先在 controller 暴露稳定接口。
- 不在 UI 线程同步触发磁盘加载/解析；需要加载时走后台线程与 service 缓存口径。

