## 目录用途
应用层装配：组织 UI/CLI/运行态模块，负责把 `engine` 的纯逻辑能力与 `plugins` 的可插拔实现组合成可运行的离线编辑器。

## 当前状态
- UI 启动装配集中在 `app/bootstrap/`，CLI 入口集中在 `app/cli/`，运行态缓存与短期状态集中在 `app/runtime/`。
- 配置与公共能力统一从 `engine` 获取；不再依赖历史 `core.*` 兼容层。

## 注意事项
- 应用层不要绕过 `engine` 公共 API 直接访问引擎内部实现细节；规则与校验应由 `engine` 维护。
- 自动化/外设能力统一通过 `app.automation.*` 访问，避免在 UI/模型层分散接入。
- 保持“只读资源（assets）/可写运行态（app/runtime）”边界清晰，避免把缓存写入资源目录。

