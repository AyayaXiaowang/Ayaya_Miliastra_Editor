# repo_root（工程根目录）

## 目录用途

- 工程顶层入口与索引：承载 `app/`（UI/CLI/运行态）、`engine/`（图引擎/校验/布局）、`plugins/`（节点实现）、`assets/`（资源库）、`docs/`（文档）、`tests/`（测试）与 `tools/`（工具链）。
- 根目录同时放置少量对外入口文件（如 `README.md`、依赖清单、许可证、CI 配置等）。

## 当前状态

- 启动入口（源码环境）：`python -X utf8 -m app.cli.run_app`（以模块方式运行，确保 `__package__/__spec__` 正确）。
- 节点图/复合节点校验：`python -X utf8 -m app.cli.graph_tools validate-graphs --all`（批量）；单文件：`python -X utf8 -m app.cli.graph_tools validate-file <path>`（也可用 `validate-graphs -f <path>`）。
- 项目存档（目录模式）校验：`python -X utf8 -m app.cli.graph_tools validate-project [--package-id <id>]`（`validate-package` 为兼容旧名）。
- `README.md`：面向使用者的主入口文档，包含依赖安装说明、最小可运行版本矩阵，以及“第三方开源项目”汇总（便于审计与追溯）。
- `LICENSES/`：第三方许可证文本副本（用于对外分发/开源发布时的审计与合规对照）。
- `pyrightconfig.json` / `pytest.ini`：静态检查与测试收集的项目级配置（应随仓库分发）。
- 项目导入/导出中心：推荐的落地方式（直接导出 `.gil` 写回 / `.gia` 导出）；UI 工具栏“导出/导入”入口依赖扩展 `private_extensions/ugc_file_tools`（未加载时会提示不可用）。
- 临时产物与对比报告等统一落在 `tmp/`（例如 `tmp/artifacts/`、`tmp/agent_todos/`）；根目录应保持“入口/索引/配置”为主，临时产物以 `.gitignore` / `.cursorignore` 为准忽略与可清理。
- Cursor 相关配置位于 `.cursor/`（本地规则与 hooks；默认被 ignore）。
- Git 上传卫生：运行期缓存/临时产物/导出物等（如 `app/runtime/cache/`、`tmp/`、`docs/`、`private_extensions/**/out/`、`assets/资源库/项目存档/_archive/`）应保持为本地可再生成或需授权的内容，不作为源码仓库提交对象；嵌套仓库目录（`private_extensions/**/.git/`）严禁进入待上传内容。
- UI Workbench bundle（`assets/资源库/项目存档/**/管理配置/UI源码/__workbench_out__/*.ui_bundle.json`）属于构建产物：写回端会读取，但应由 HTML 重新生成，避免把旧 bundle 提交进仓库导致协作环境使用陈旧产物。
- `ugc_file_tools` 本地样本与解析状态：`private_extensions/ugc_file_tools/save/`、`private_extensions/ugc_file_tools/parse_status/`、以及 UI schema library 沉淀数据 `private_extensions/ugc_file_tools/ui_schema_library/data/` 默认视为本地输入样本/可再生成视图；对外仓库默认忽略。运行必需/默认依赖的 seed 版本化收口在 `private_extensions/ugc_file_tools/builtin_resources/`（见根目录 `.gitignore`）。
- 对外开源发布：在内容/授权未确认前，`assets/资源库/共享/**`、`assets/ocr_templates/**`、以及活跃项目存档（如 `assets/资源库/项目存档/第七关/**`、`assets/资源库/项目存档/锻刀/**`）默认不随仓库上传；确认可公开后再做白名单放开。
- `tools/`：同时包含通用审计脚本与内部/项目专项脚本；对外发布默认通过根目录 `.gitignore` 排除“依赖 `private_extensions/ugc_file_tools` 的工具脚本”与“Level7/第七关等内容生产脚本”。

## 注意事项

- PowerShell 不支持 `&&`，多条命令请逐行执行。
- 根目录文件保持“入口/索引/配置”属性；诊断证据链请写入 `docs/diagnostics/`（本地留存，不随仓库上传）。
- 根目录不放静态前端资源（HTML/CSS/JS）。Web 工具的静态资源应随工具目录分发，或落在 `assets/` 下的对应真源目录。
- 上传前复核：即使 `.gitignore` 已覆盖产物目录，也应在上传前再次确认不存在临时/导出/缓存/归档数据被误加入（尤其是 `private_extensions/**/out/` 与 `assets/资源库/项目存档/_archive/`）。
- 对外发布前建议再跑一次 `python -X utf8 -m tools.find_hardcoded_absolute_paths`，避免示例/工具脚本里残留本机绝对路径。
- Git配置自身忽略：`.gitignore` 和 `.cursorignore` 已被配置为忽略上传，避免本机的配置文件变动被提交到仓库。
- 本文件仅描述“目录用途 / 当前状态 / 注意事项”，不记录修改历史。
