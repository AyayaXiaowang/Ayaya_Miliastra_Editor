## 目录用途
- `layout_templates.py` 的拆分实现区：承载 UI 写回相关的“布局/record 操作”与控件组/模板能力，供 Web UI 导入、schema clone、layout 资产导出等链路复用。

## 当前状态
- `shared.py`：对外稳定薄门面；实现已拆到 `shared_parts/`（lossless dump、最小 patch 写回、layout registry、GUID/children(varint) 操作、meta blob13、RectTransform 等）。
- `control_groups.py`：对外稳定薄门面；实现已拆到 `control_groups_parts/`（打组、保存模板、模板实例化放置、层级写回）。
- `layout_create.py`：新增布局 root（默认克隆基底布局的固有 children）。
- `progressbar_templates.py`：进度条模板创建/放置。

## 注意事项
- 不使用 try/except；写回目标结构不一致直接抛错（fail-fast）。
- 写回输出统一写入 `ugc_file_tools/out/`，不要覆盖原 `.gil`。
- **模板 root 注册顺序（重要）**：将模板 root GUID 写入 `4/9/501[0]`（layout registry）时必须保持既有模板 roots 顺序稳定；新模板 root 插入到现有模板 roots 之后。
- `shared.py` 对外提供公开别名（无下划线）供跨模块复用；外部禁止依赖 `shared_parts/*` 或 `control_groups_parts/*` 具体路径。
