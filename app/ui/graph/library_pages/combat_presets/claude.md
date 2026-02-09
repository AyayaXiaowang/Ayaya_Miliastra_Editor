## 目录用途
`ui/graph/library_pages/combat_presets/` 存放战斗预设页面拆分出的配套模块，包括通用对话框和按类型划分的业务处理器，供主界面复用。

## 当前状态
- `dialogs.py`：定义玩家职业、角色、技能、投射物、单位状态与道具的表单对话框，支持自定义标题与初始数据，新增/编辑复用同一套控件。
- `sections.py`：封装战斗预设各分类（玩家模板、职业、技能、本地投射物、单位状态与道具）的行构建、增删改逻辑，并提供统一的注册表；编辑流程统一调用上述表单对话框，不再散落手写 QDialog；新建记录时会同时更新当前视图模型（`PackageView` / `GlobalResourceView` 的 `combat_presets`) 与底层 JSON 资源：各 Section 的 `create_item` 在生成规范 ID 与默认名称后，通过视图上的 `resource_manager.save_resource(ResourceType.PLAYER_TEMPLATE/PLAYER_CLASS/UNIT_STATUS/SKILL/PROJECTILE/ITEM, ..., resource_root_dir=...)` 立即将配置写入对应资源根目录（PackageView→当前项目存档根，GlobalResourceView→共享根），避免落入默认归档项目导致当前视图不可见；项目存档视图下，`PackageController._sync_combat_presets_to_index` 仍负责在“保存存档”时根据视图模型覆盖 `PackageIndex.resources.combat_presets[...]` ID 列表，使存档与资源之间的引用关系与资源本体解耦；为方便排查战斗预设在各分类中的新增与数量变化，所有 Section 在 `create_item` 中都会打印带有 `[COMBAT-PRESETS]` 前缀的调试日志，包含当前视图标识、生成的 ID、默认名称与创建前后条目数量。
- `__init__.py`：导出常用的 Section 列表、查找方法与表格结构体，便于 `combat_presets_widget` 调用。

## 注意事项
- 任何 UI 交互都应通过本目录的对话框或 Section 方法实现，保持主界面文件的简洁。
- Section 方法应返回布尔值指示是否修改了数据，以便调用方决定是否刷新。
- 扩展新分类时，请在 `sections.py` 中注册新 Section，并保持 `claude.md` 对目录用途的描述同步。
- 各 Section 新建实体（职业/角色/技能等）时统一调用 `app.ui.foundation.id_generator.generate_prefixed_id()`，避免手写时间戳带来的重复。


