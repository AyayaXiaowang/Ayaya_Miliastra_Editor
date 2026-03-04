## 目录用途
存放复合节点（Composite）相关测试：覆盖复合节点文件发现策略、管理器依赖护栏、模板示例结构与引脚类型策略等，避免复合节点体系与节点库/管线入口出现漂移。

## 当前状态
- `test_composite_file_discovery_policy.py`：回归复合节点定义文件发现/筛选规则的单一事实来源，确保 policy、pipeline discovery 与 CompositeNodeManager 加载集合一致。
- `test_composite_manager_no_registry_backedge.py`：回归 CompositeNodeManager 工厂不得隐式调用 NodeRegistry 等反向依赖，避免循环依赖与缓存不一致。
- `test_composite_multi_pins_template.py`：解析并校验 `composite_多引脚模板_示例.py`，回归虚拟引脚类型/方向、分支出口映射与关键计算节点生成符合设计；并确保模板示例可通过 `engine.validate.api.validate_files` 的引擎校验，避免规则/缓存漂移导致示例无法自检。
- `test_composite_pin_direction_policy.py`：回归复合节点引脚方向策略：payload 虚拟引脚方向与 mapped_ports 必须一致；类格式入口方法同名引脚禁止同时作为数据入与数据出（数据入不能设置为出引脚）；并回归禁止“数据出变量=数据入/入口形参”的纯透传写法。
- `test_composite_pin_type_policy.py`：回归复合节点引脚类型策略：泛型/列表/字典泛型/Any/旧别名与 Python 内置类型名等占位类型在成品校验期必须报错。
- `test_composite_folder_manager_path_safety.py`：回归复合节点库文件夹“新建/删除”的路径安全约束，禁止路径穿越与绝对路径/UNC/盘符注入。
  - 用例避免在源码中写死盘符绝对路径；盘符注入样本由运行时环境推导生成。
- `test_composite_manager_reload_library_from_disk.py`：回归 `CompositeNodeManager.reload_library_from_disk()`：当外部修改 `复合节点库/**/*.py` 后，管理器可重新扫描并更新内存索引（不依赖重启进程）。
- `test_composite_flow_exit_mapping_ignores_loop_body_terminals.py`：回归类格式复合节点的流程出虚拟引脚映射：循环体内部“无出边流程端口”应视为 continue（本次迭代结束），不能被误当作方法级流程出口绑定到虚拟流程出上。
- `test_composite_port_same_type_rule.py`：回归复合节点源码内的同型输入约束：`拼装列表` 混用类型（整数≠浮点数）时必须报错（`PORT_SAME_TYPE_REQUIRED`）。

## 注意事项
- 复合节点相关测试通常会构造最小源码片段或引用公开模板文件，保持输入稳定可复现。


