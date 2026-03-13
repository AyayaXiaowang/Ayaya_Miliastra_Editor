## 目录用途
存放仓库护栏/基础契约类测试与扫描脚本，防止基础约束回退。

## 文件清单
- __pycache__/：字节码缓存
- claude.md：目录说明
- scan_non_test_project_asset_refs.py：扫描存档引用
- test_codegen_sys_path_bootstrap.py：codegen 引导护栏
- test_contract_node_graph_type_mappings.py：类型映射契约
- test_executable_codegen_closure_validate.py：codegen 闭环回归
- test_export_claude_md_paths.py：claude 路径导出
- test_gia_export_asset_bundle_golden_snapshot.py：GIA 导出金样
- test_gia_export_composite_pin_index.py：GIA 复合 pin
- test_gia_export_enum_mapping.py：GIA 枚举映射
- test_gia_export_multibranch_cases_outflows.py：GIA 多分支回归
- test_gia_export_ui_state_group_missing_optional_policy.py：GIA UIKey 回填
- test_gil_writeback_assembly_dict_concrete_id.py：拼装字典写回
- test_gil_writeback_dict_outparam_requires_kv_failfast.py：字典 KV 缺失报错
- test_gil_writeback_dict_port_type_alignment.py：字典端口对齐
- test_gil_writeback_local_var_and_dict_type_inference_regressions.py：推断回归夹具
- test_gil_writeback_pipeline_signal_specific_type_id_opt_in_plumbing.py：写回策略开关
- test_gil_writeback_prefers_node_def_key_type_id.py：node_def type_id
- test_gil_writeback_snapshot_fields_fallbacks.py：快照字段兼容
- test_gil_writeback_sync_with_gia_rules.py：GIL/GIA 对齐
- test_import_path_single_source_of_truth.py：导入路径护栏
- test_no_core_subpackages.py：禁止 core 目录
- test_no_ui_direct_in_memory_graph_payload_cache_import.py：UI 缓存导入护栏
- test_node_graphs_importer_explicit_graph_id_assignment.py：graph_id 赋值
- test_node_registry_load_guards.py：节点库加载护栏
- test_node_stub_pyi_up_to_date.py：节点类型桩一致
- test_port_type_event_migration_scan_command_logic.py：端口迁移扫描
- test_port_type_title_fallback_scan_command_logic.py：title 扫描回归
- test_project_export_gia_signal_collection.py：GIA 信号收集
- test_project_writeback_ui_before_graphs.py：UI 写回顺序
- test_python_syntax_compilable.py：全仓语法检查
- test_recent_exported_gils_registry.py：导出清单回归
- test_signal_exporter_field6_fallback.py：信号导出兼容
- test_type_registry_alignment.py：类型注册表对齐
- test_ui_key_placeholder_global_var_type_inference.py：UIKey 占位符
- test_ui_state_group_missing_show_optional_writeback_policy.py：状态组回填
- test_ui_state_hidden_alias_rebind.py：UI 状态别名
- test_ui_state_hidden_optional_writeback_policy.py：UI 状态策略
- test_validate_graphs_all_includes_port_type_regression_samples.py：targets 收集回归
- test_vector3_none_constant_writeback.py：Vec3 None 常量
- test_writeback_id_ref_placeholders_missing_optional_policy.py：占位符放行
- test_writeback_ui_guid_registry_autoload.py：UI registry 加载

## 注意事项
- [全局] 护栏类测试应避免污染工作区。
- [全局] 需要写入时使用 `tmp_path`。
