# 目录用途
只读资源与模板（图、实体、预设、知识库、模板等），与应用的可写运行态分离。

# 子目录
- `资源库/`：UGC 资源总库（元件库、实体摆放、节点图、战斗预设、管理配置等）
- `ocr_templates/`：OCR 模板资源（仅静态图片与子目录）
- `ui_workbench/`：占位目录（不再维护完整 Workbench 前端实现）；实际的 Web-first 工具由私有扩展 `private_extensions/千星沙箱网页处理工具` 提供并在运行期注入入口

# 公共 API
无（数据供上层加载）。

# 依赖边界
- 资源读写统一通过 `engine.resources` 下的资源管理与索引服务（例如 `ResourceManager`、`ResourceIndexBuilder` 等）完成，上层应用与工具不直接以裸 `open()` 访问资源文件。

# 当前状态
- 仓库仅收录少量示例/教学资源（节点图、战斗预设、管理配置等），完整工作资源按 `.gitignore` 规则保存在本地；缺失的索引或缓存可由资源管理工具按需重建。
- `ocr_templates/` 按 profile 子目录提供模板示例（如 `1080-100-CN` / `1080-125-CN` / `2K-100-CN` / `2K-125-CN` / `4K-100-CN` / `4K-125-CN`；legacy 允许 `4K-CN` 但当前仓库未收录）；新增分辨率/缩放支持时在同级补充对应 profile 目录即可。
- 资源库结构保持稳定，`ResourceManager` / `PackageIndexManager` 在首次访问时会生成/刷新必要的索引与缓存。
- `ui_workbench/` 仅为只读占位资源；运行期不会写入本目录，所有缓存统一落在 `settings.RUNTIME_CACHE_ROOT`。

# 注意事项
- 中文路径与文本统一使用 UTF-8；代码中读取时显式 `encoding="utf-8"`。
- 本目录视为只读资源库，运行态产物与缓存统一写入运行时缓存根目录（`settings.RUNTIME_CACHE_ROOT`，默认 `app/runtime/cache/`）。
- 路径与结构保持稳定，避免在本目录内嵌套同名子树。 


