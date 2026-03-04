# 贡献指南

本仓库是面向原神“千星奇域”的离线沙箱编辑器与 Graph Code 工具链。

对大多数使用者来说：**只需要编写节点图 Graph Code，不要修改引擎（engine/）/工具链代码**（见 `docs/用户必读.md`）。  
如果你发现了引擎 BUG，推荐先通过 Issue/群反馈给作者并提供最小可复现；如确需提交代码改动，请先开 Issue 与作者对齐方向。

## 你可以贡献什么
- 反馈问题并提供**最小可复现**（优先：报错输出 + 单文件复现）
- 为重要规则补充回归测试（优先）
- 改进用户文档（例如 `README.md`、`docs/用户必读.md`、各公开目录的 `claude.md`）
- 在 Issue 讨论达成一致后，提交引擎/工具链的 bug 修复或改进

## 你不应该提交什么
- 任何私密资源、账号信息、Token、截图、个人工程存档
- 不应公开的资源库内容（例如本地私有 `assets/资源库/` 资源、OCR 模板、个人项目存档等）
- 运行期缓存与本地状态（见根目录 `.gitignore`）

## 开发环境
- Windows 10/11
- Python 3.10 - 3.12（推荐 3.10.x，不支持 3.13）
- 依赖安装（PowerShell，逐行执行）：

```powershell
pip install -r requirements-dev.txt -c constraints.txt
```

## 运行测试

```powershell
python -X utf8 -m pytest
```

## 节点库变更（重要：SoT + 可回归）

当你修改以下目录时，视为“节点库变更”（端口/类型/约束/语义/兼容性都会影响历史资产）：
- `plugins/nodes/**`（基础节点：`@node_spec(...)` 为单一事实源）
- `assets/资源库/共享/复合节点库/**` 与 `assets/资源库/项目存档/<项目存档名>/复合节点库/**`（复合节点：同属节点库的一部分）

### 必跑护栏（推荐用一键入口）

```powershell
# 运行回归测试
python -X utf8 -m pytest

# 校验（单文件调试，开发期推荐）
python -X utf8 -m app.cli.graph_tools validate-file <对应文件路径>

# 校验（节点图/复合节点 + 项目存档，全量扫描）
python -X utf8 -m app.cli.graph_tools validate-graphs --all
python -X utf8 -m app.cli.graph_tools validate-project
```

说明：
- `tests/snapshots/node_library_manifest.json` 为节点库 manifest baseline（不建议手工编辑；如需变更请走维护流程）。
- `docs/generated/node_library/` 为自动生成参考文档（端口/类型/约束等接口真相），禁止手工编辑。

### 兼容性约定（避免 breaking）

- **节点改名**：优先通过 `@node_spec(..., aliases=[...])` 保留旧名作为别名，避免历史 Graph Code/图资产断裂。
- **端口改名**：必须在 `@node_spec` 中声明端口别名：
  - `input_port_aliases={"新端口": ["旧端口"]}`
  - `output_port_aliases={"新端口": ["旧端口"]}`
  这样 manifest diff 会把改名识别为“可迁移/可兼容变更”，Graph Code 迁移工具也能自动改写关键字参数名。

## 节点图/复合节点的校验（提交前建议）
如果你新增/修改了节点图或复合节点源码，请在提交前运行校验并根据输出修正：

```powershell
python -X utf8 -m app.cli.graph_tools validate-graphs --all
```

> 注意：不要直接运行 `run_app.py` 这类入口；工具脚本与校验脚本请使用 `python -m ...` 的模块方式运行。


## 目录约定（重要）

- 每个公开目录都有一个 `claude.md`，用于描述“目录用途 / 当前状态 / 注意事项”（不写修改历史）。
- 资源库采用“默认忽略 + 白名单放行示例”的策略：不要扩大白名单范围，除非明确确认资源可公开且不会泄露隐私。


