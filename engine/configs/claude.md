## 目录用途
引擎配置（定义 / Schema / 默认值）的集中地：全局 settings、资源类型枚举、规则与类型占位、各领域配置数据模型等。这里只描述配置结构，不存放实例化数据或环境私有配置。

## 当前状态
- `settings.py`：全局设置与开关（布局/校验/资源刷新/运行期缓存根等）；启动入口需先调用 `settings.set_config_path(workspace_root)` 注入工作区根目录，供布局与缓存路径派生使用；其中 `PRIVATE_EXTENSION_ENABLED` 会按配置文件生效（不再在 load 阶段强制覆盖）。
- `resource_types.py`：资源类型枚举，供资源层与上层统一引用。
- 领域配置子包：`rules/`、`components/`、`combat/`、`management/`、`entities/`、`specialized/`（均以 `dataclass`/常量为主）。
- `ingame_save_data_cost.py`：局内存档数据量开销估算（纯逻辑），供校验/工具链复用。

## 注意事项
- 本目录仅定义“配置/Schema/常量”，避免引入运行时副作用逻辑；禁止依赖 `app/*`、`plugins/*`、`assets/*`。
- 路径相关设置（如 `settings.RUNTIME_CACHE_ROOT`）是唯一真源，业务模块不要自行硬编码缓存路径。
- 注释/说明避免写外部知识库的具体路径或 URL；不使用 `try/except` 吞错。

