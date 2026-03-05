# ugc_file_tools/builtin_resources/seeds

## 目录用途

- 存放 `ugc_file_tools` 写回/导出链路直接依赖的 **最小 `.gil` seed**（作为“克隆原型 / bootstrap 模板 / node_def 模板”）。
- 这些文件应随仓库分发：缺失应 fail-fast 抛错；不应包含未授权业务内容，仅作为结构模板/夹具。

## 当前状态

- `infrastructure_bootstrap.gil`：基础设施段 bootstrap 模板（补齐 root4/11、root4/35 等缺口；只补缺失，不覆盖业务段）。
- `template_instance_exemplars.gil`：模板/实例导入的克隆原型（偏向包含 `type_code=10005018` 的“空模型元件”样本）。
- `struct_def_exemplars.gil`：基础结构体字段原型 seed（用于选择覆盖 type_id 更全的结构体作为字段 entry 原型源）。
- `ingame_save_structs_bootstrap.gil`：局内存档结构体导入的自举模板（当目标存档 root4/10/6 为空时用于补齐结构体系统模板基底）。
- `signal_node_def_templates.gil`：信号写回的默认 node_def 模板（需包含至少一个“无参数信号”的 3 类 node_def 样本：send/listen/send_to_server）。

## 注意事项

- 保持最小化：仅收纳默认链路必需且可公开的 seed；实验/真源样本请放在 `ugc_file_tools/save/` 并默认忽略。
- 本目录 `.gil` 已被裁剪为“仅保留写回链路必需的 payload_root 顶层字段集合”，用于降低体积与误入库风险。
- 如需重新裁剪/重建，请使用脚本：`python -X utf8 -m tools.minimize_ugc_file_tools_seed_gils [--apply]`（写盘前会备份到 `tmp/artifacts/`）。
- 写回/导出产物统一落到 `ugc_file_tools/out/`，避免覆盖样本输入。
