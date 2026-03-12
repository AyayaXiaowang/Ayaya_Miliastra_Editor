## 目录用途
存放可命令行运行的单元测试与轻量回归用例，用于验证引擎与工具链关键契约。

## 文件清单
- __init__.py：tests 包标记
- __pycache__/：字节码缓存
- _helpers/：测试辅助模块
- arch/：架构约束测试
- automation/：自动化协议测试
- common/：通用契约测试
- composite/：复合节点测试
- conftest.py：pytest 配置
- graph/：图语义回归
- layout/：布局回归测试
- local_sim/：本地模拟测试
- resources/：资源扫描测试
- shape_editor/：形状编辑测试
- snapshots/：快照数据
- todo/：todo 逻辑测试
- tooling/：仓库护栏测试
- ugc_file_tools/：ugc 工具测试
- ui/：UI 冒烟测试
- validate/：校验规则测试
- claude.md：目录说明

## 注意事项
- [全局] 资源依赖必须可复现：优先使用 `tmp_path`，否则落在 `assets/资源库/项目存档/测试项目/`。
- [全局] 需要仓库根目录时使用 `tests._helpers.project_paths.get_repo_root()`。
- [全局] 禁止将 `<repo>/app` 加入 `sys.path`，统一从 `app.*` 导入。
