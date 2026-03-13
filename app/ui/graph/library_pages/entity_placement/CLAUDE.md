## 目录用途
`app/ui/graph/library_pages/entity_placement/`：实体摆放页面（`EntityPlacementWidget`）的拆分实现，按“UI装配/页面协议/列表构建/关卡实体/实例操作/装饰物合并”等职责拆成多个 mixin 与工具模块，降低单文件复杂度并便于复用与测试。

## 当前状态
- **入口类**：`app/ui/graph/library_pages/entity_placement_widget.py` 仅保留 `EntityPlacementWidget` 壳与信号定义，并通过组合 mixin 提供完整能力。
- **常量集中**：页面相关的 item role、分类 key、对话框尺寸、向量范围与格式化参数统一收敛到 `constants.py`，避免散落魔法数字。
- **实现拆分**：各 mixin 只负责自身职责（例如快捷键/上下文菜单、列表刷新与选中恢复、关卡实体专用逻辑、装饰物合并工作流），写盘/索引移动仍委托 `ResourceManager`/`PackageIndexManager` 等上层组件。
- **模块划分**：`ui_mixin.py`（UI/快捷键/菜单）、`protocol_mixin.py`（页面协议/选中联动）、`instance_list_mixin.py`（列表构建与共享徽章）、`level_entity_mixin.py`（关卡实体）、`instance_ops_mixin.py`（增删改移动等操作）、`merge_decorations_mixin.py`（装饰物合并工作流）。

## 注意事项
- mixin 内不做静默降级或 try/except 吞错；错误应显式抛出或通过既有 UI 提示链路暴露。
- 列表重建必须复用 `rebuild_list_with_preserved_selection` 以保证“信号阻塞 + 选中恢复”语义稳定，避免右侧面板联动抖动。
- 涉及资源归属移动/删除的语义需继续区分 `PackageView` 与 `GlobalResourceView`，不要在页面层直接散落文件 I/O。

