## 目录用途
节点图库（`GraphLibraryWidget`）的子模块：将目录树与图列表等领域逻辑拆分为 mixin，主组件聚焦于 UI 装配与状态管理。

## 当前状态
- **目录树**：`folder_tree_mixin.py` 负责构建与维护文件夹树（当前项目/共享扁平同级展示，当前在前、共享在后；共享目录名带 `🌐` 标记），并记录展开状态；在可编辑会话下支持文件夹 CRUD 与拖拽移动。
- **图列表**：`graph_list_mixin.py` 负责图卡片列表、筛选/排序、选中/双击打开与图级操作（新建/复制/重命名/删除/移动）。列表刷新采用缓存与增量更新，避免大图量下频繁重建 QWidget。
- **异步元信息与加载**：切目录/刷新时可后台补全 Graph metadata；打开图时通过异步 loader 在后台线程加载 `ResourceManager.load_resource(...)`，并提供取消/防串包语义。
- **只读语义**：默认以浏览为主；只读模式下禁用写入类动作，并引导用户在资源库的 Python Graph Code 文件中维护节点图源码。
- **路径口径**：folder_path 文本归一化统一复用 `engine.utils.path_utils.normalize_slash`。

## 注意事项
- 图元信息只能走轻量解析（如 `load_graph_metadata()`），禁止执行节点图源码。
- 资源读写统一通过 `ResourceManager` 与 `PackageIndexManager`；不在本目录直接改写索引或拼路径写文件。
- 确认/提示类弹窗统一走 `ConfirmDialogMixin` / `app.ui.foundation.dialog_utils`；非关键反馈优先使用 Toast。
- 与外部交互通过 `GraphLibraryWidget` 信号（选择/打开/跳转请求），避免反向依赖主窗口或编辑器控制器。


