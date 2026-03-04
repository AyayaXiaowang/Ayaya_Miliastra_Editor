# app/cli/commands

## 目录用途

`app.cli.graph_tools` 的子命令实现与注册：按领域拆分具体命令模块，入口只负责解析 `--root`、初始化 settings、注册子命令并分发执行。

## 当前状态

- 命令模块约定提供 `register(subparsers)`，并通过 `parser.set_defaults(_runner=...)` 绑定执行函数。
- runner 统一签名：`runner(parsed_args, workspace_root) -> int`；统一注册入口位于 `app.cli.commands`。
- `scan-title-fallback`：离线诊断/迁移辅助命令；显式扫描 GraphCode 中“NodeDef 定位是否依赖 title fallback”，输出 JSON 报告到 `tmp/artifacts/`（仅用于迁移/兼容诊断，交付边界默认禁止 title fallback）。
- `scan-event-migration`：离线诊断/迁移辅助命令；扫描 GraphCode 中 `node_def_ref.kind="event"` 的节点，按 `category/title -> builtin_key` 规则判断是否可迁移为 builtin ref，并输出 JSON 报告到 `tmp/artifacts/`（仅输出清单与统计，不改写源码）。
- `sync-custom-vars`：refs-only，同步引用点与第三方存放实体资源（变量 Schema 真源为注册表，虚拟变量文件由引擎侧提供）。
- `apply-ui-defaults`：写回目标为 `自定义变量注册表.py`（注册表真源），不再生成/写入 `UI_*_自动生成.py` 作为 Schema 真源。
- `validate-ui`：只做 UI 占位符语法/存在性校验（不写盘、不提供 `--fix` 自动生成变量定义）。
- `sync-ui-vars`：只做 `validate-ui` +（可选）`apply-ui-defaults --all` + 再次 `validate-ui`（不再生成变量定义）。
- `cursor-agent` / `cursor-models`：对接本机安装的 Cursor Agent CLI（`agent`），用于从 `graph_tools` 透传调用与模型枚举。

## 注意事项

- 不在模块顶层推导 `workspace_root` 或初始化 settings；避免 import 阶段副作用影响其它工具/测试。
- 命令应优先调用 `engine` 的公共 API，不在 CLI 层复制业务规则。
- 依赖 `ugc_file_tools` 私有扩展的命令需先导入 `private_extensions.ugc_file_tools`，以触发顶层包 alias 与 import-root 注入（避免直接 `import ugc_file_tools` 时在纯源码环境报 `ModuleNotFoundError`）。
