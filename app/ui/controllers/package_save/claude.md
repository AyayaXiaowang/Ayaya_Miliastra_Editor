## 目录用途
`ui/controllers/package_save/` 负责承载“存档保存链条”的可组合服务（service）实现，把事件编排与写盘细节从 `PackageController` 中拆出去，降低 God Object 体积与多人协作冲突面。

## 当前结构
- `save_orchestrator.py`：保存事务编排（指纹基线同步 → 可选 flush → special_view / package_view 分支 → 结果回传）
- `fingerprint_baseline_service.py`：保存前/后资源库指纹基线同步策略：保存前仅在检测到“内部写盘导致的指纹脏标记”时同步基线（避免吞掉真实外部变更）；保存确实写盘后刷新基线以反映最新落盘状态
- `resource_container_save_service.py`：模板/实体摆放/关卡实体容器的资源写回（ResourceManager.save_resource）
- `special_view_save_service.py`：全局视图（global_view）下的写回逻辑
- `package_view_save_service.py`：具体存档视图（PackageView）下的写回逻辑（组合子服务并汇总写盘结果）
- `combat_presets_save_service.py`：战斗预设保存与索引同步：
  - `save_preset_resources(...)`：按条目保存战斗预设资源本体（不修改 PackageIndex），用于战斗详情面板的增量落盘
  - `sync_to_index(...)`：仅同步 `PackageIndex.resources.combat_presets` 的引用列表（不保存资源本体），用于库页增删改引发的引用变更
- `signals_save_service.py`：信号摘要与聚合资源写回（`PackageIndex.signals`）
- `management_save_service.py`：管理配置写回资源库与 `PackageIndex.resources.management`；对“新建且此前无文件落点”的管理资源，默认写入当前项目存档根目录，避免落入默认归档项目导致当前视图不可见。
- `package_index_persist_service.py`：索引持久化与指纹基线刷新（目录模式下不再写回 `pkg_*.json`；主要写入运行期状态并更新派生缓存）。

## 注意事项
- 本目录服务不依赖具体 Widget；与 UI 交互通过主窗口注入的回调（flush、请求保存当前图等）完成。
- 不在 service 内做“吞异常”或 try/except；遇错直接抛出，由上层统一处理。
- 顺序边界以 `save_orchestrator` 为唯一真源：不要在其他地方复制/分叉保存阶段顺序。
- 保存冲突策略对齐 VSCode：当容器对象上存在 `_source_mtime` 基线时，`ResourceContainerSaveService` 会在写盘时把它作为 `expected_mtime` 传给 `ResourceManager.save_resource`；若磁盘已被外部修改则默认拒绝覆盖（返回 False）并跳过“已保存”日志，避免静默覆盖。
- `PackageIndexPersistService.persist()` 会尊重 `save_package_index` 的返回值：索引未写入时不刷新指纹基线，并由 `PackageViewSaveService` 直接返回 False 以避免上层误判为“已保存”而清空 dirty_state。


