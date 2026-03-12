## 目录用途
应用层装配：组织 UI/CLI/运行态模块，组合引擎与插件能力形成可运行应用。

## 文件清单
- __pycache__/：缓存产物
- automation/：自动化执行
- bootstrap/：启动装配
- cli/：命令行入口
- codegen/：代码生成
- common/：公共工具
- models/：数据模型
- runtime/：运行态服务
- ui/：桌面界面
- __init__.py：包入口
- __main__.py：模块入口
- app_info.py：应用信息
- claude.md：目录说明

## 注意事项
- [全局] 应用层只使用引擎公共 API，禁止依赖引擎内部实现细节。
- [全局] 自动化能力统一通过 `app.automation.*` 访问，避免在 UI/模型层分散接入。
- [全局] 只读资源与运行态缓存边界清晰，禁止把缓存写入资源目录。