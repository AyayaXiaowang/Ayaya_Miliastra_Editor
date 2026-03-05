## 目录用途
`ui/controllers/package_save/` 承载“存档保存链条”的可组合 service：把事件编排与写盘细节从 `PackageController` 中拆出去，降低耦合与单文件体积。

## 当前状态
- **事务编排**：`save_orchestrator.py` 作为保存顺序与边界的单一真源（指纹基线同步 → 可选 flush → special_view/package_view 分支 → 结果回传）。
- **指纹基线策略**：`fingerprint_baseline_service.py` 统一保存前/后的指纹基线同步，避免吞掉真实外部变更并在确认写盘后刷新基线。
- **资源写回**：`resource_container_save_service.py`（模板/实体摆放/关卡实体容器写回）、`special_view_save_service.py`（global_view 写回）、`package_view_save_service.py`（PackageView 写回与结果汇总）。
- **战斗预设**：`combat_presets_save_service.py` 区分“按条目保存资源本体”与“仅同步索引引用列表”，避免不必要的全量写盘。
- **信号与管理配置**：`signals_save_service.py` 写回信号摘要/聚合资源；`management_save_service.py` 写回管理资源并在新建无落点时默认写入当前项目存档根目录以保证可见性。
- **索引持久化**：`package_index_persist_service.py` 负责运行期状态与派生缓存持久化，并在需要时刷新指纹基线。

## 注意事项
- service 不依赖具体 Widget；与 UI 交互通过主窗口注入的回调（flush、请求保存当前图等）完成。
- 不在 service 内做 `try/except` 吞错；遇错直接抛出，由上层统一处理。
- 保存冲突策略对齐 VSCode：当存在 `_source_mtime` 基线时写盘会传入 `expected_mtime`，磁盘已被外部修改则拒绝覆盖，避免静默覆盖用户改动。
- `save_orchestrator` 是保存顺序的唯一真源；不要在其它模块复制/分叉保存阶段顺序。

