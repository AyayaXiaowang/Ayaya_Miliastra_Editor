## 目录用途
- 收敛“端口”相关的数据结构与操作逻辑：端口检测、筛选、类型推断、类型设置等。
- 作为自动化执行与参数配置阶段之间的“端口抽象层”，尽量屏蔽底层视觉识别细节。

## 当前状态
- 主要模块（端口类型与配置相关流程会配合统一的短暂等待与画布吸附策略，避免在 UI 仍未稳定或节点上方误点时继续后续步骤）：
  - `port_types.py`：端口检测结果与相关类型定义，包含位置、侧别、模板种类、同侧序号以及可选的匹配置信度（confidence，0~1，用于调试展示“这次识别有多可信”）。
  - `_ports.py`：端口种类归一化与通用判定/筛选函数，内置中英文关键字映射，并基于归一化结果统一判断流程/数据端口及行内元素（Settings/Select/Warning 等）；对于“信号名/结构体名”这类在引擎层被视为“选择端口”的输入行，会在数据输入端口集合中显式排除，使屏幕候选与 `engine.graph.common.is_selection_input_port` 语义保持一致；通过 `PortKind` / `PortCategory` 与 `get_port_category()` 将底层 kind / side / 中文名组合成高层语义分类（数据/流程输入输出与行内控件），并提供 `get_port_center_*()` 等几何辅助函数；按侧别与 kind 过滤可连接端口候选的通用工具也集中在此处，供 `port_picker`、配置步骤与连接匹配等模块复用，杜绝各处私有判断。
- `port_picker.py`：在识别到的端口列表中选择合适的端口中心，侧别/可连接性与类型筛选统一委托 `_ports.filter_ports_for_screen_candidates` 作为单一入口，其余多级回退策略围绕命名、序号、数字端口名与索引等信息按固定优先级顺序依次尝试；端口几何排序与“期望为 flow/data 时的种类校验”基于 `_ports.get_port_center_y()` 与 `_ports.get_port_category()`，并通过内部 `_pick_candidate_with_kind_preference` 工具在命名/索引等策略中统一实现“优先选同 kind，再回退到首个候选”的逻辑；日志输出则通过 `app.automation.editor.executor_utils.make_executor_log_fn` 构造基于 `executor._log(..., log_callback)` 的闭包，保持各策略日志前缀与回调使用方式一致；当某一帧端口识别结果为空且运行在真实编辑器执行器环境下时，会优先基于节点中心在画布区域内寻找安全空白点，将鼠标移出节点到该空白位置后重新截图并重试一次端口识别，以降低因鼠标遮挡或节点局部 UI 状态导致的“无端口候选”失败。
- `settings_locator.py`：集中管理 Settings 端口的收集与中心点挑选逻辑，并提供按侧别与行中心在节点区域内搜索模板图标的辅助函数；行内元素所在行的粗筛选与横向几何约束统一复用 `_ports.get_port_center_*()` 与 `_ports.get_port_category()`，以与端口挑选模块保持一致的判定标准。
- `dict_port_type_steps.py`：封装字典端口类型设置步骤，通过 Dictionary 图标与“键/值”标签模板完成键/值类型选择，并与画布交互/吸附工具协同；相关模板路径由执行器的 `ocr_template_profile` 决定（避免硬编码 `4K-CN`）；内部按“确认 Dictionary 图标与必要的类型切换 / 打开字典设置对话框 / 应用键/值类型 / 点击画布空白结束配置”拆分为职责单一的助手函数；键/值标签点击后的“类型搜索 + 选择”流程复用 `port_type_ui_core.apply_type_in_open_search_dialog`，在单次字典配置过程中共享对话框截图与模板匹配结果，减少重复 OCR/模板匹配；当端口尚未被声明为“字典”时，会通过 `port_type_ui_core.set_port_type_with_settings` 先将端口类型切换为基础“字典”，再重新截图查找 Dictionary 图标，避免在高层步骤模块之间引入循环依赖；与其它端口类型 UI 步骤一致，日志回调与暂停/终止钩子等运行时上下文统一经 `app.automation.editor.executor_protocol.AutomationStepContext` 传递，避免在多个 helper 之间重复维护参数组合。
- `_add_ports_common.py`：收敛端口新增相关的通用小工具，包含节点解析、基础新增数量计算与统一的 `execute_add_ports_generic()` 骨架函数，供变参端口与字典端口在同一套“解析节点 → 计算最终 add_count → 点击 Add 图标”流程上复用；具体“如何从当前端口数量与目标数量推导最终新增数量”通过策略回调传入，避免在各模块中重复实现相同的统计与日志逻辑。
- `variadic_ports.py` / `dict_ports.py`：变参端口和字典端口的新增与管理，共用 `_add_ports_common.execute_add_ports_generic()` 完成节点解析、最终新增数量计算与 Add 图标点击；变参端口在统计当前端口数量时统一复用 `NodePortsSnapshotCache` 提供的节点端口快照，并结合 `_ports.is_data_input_port` 与端口 `name_cn` 的数字匹配筛选左侧数字数据输入行作为变参端口集合，再依据 Todo 中的目标数量计算最终新增数量；字典端口则直接使用 Todo 中给定的 `add_count`，二者在日志前缀与 `prefer_multi` 策略上保持一致。
  - 节点定位失败时，`port_type_setter.py` 会根据当前程序坐标绘制期望位置矩形并在监控面板上高亮，便于排查“未能定位节点”的原因。
  - `port_type_common.py`：端口类型推断通用工具与基础/列表类型映射，集中收敛“泛型家族/流程类型”等通用类型名判定逻辑；其中基础→列表映射的唯一事实来源为 `engine/type_registry.py`（本模块内以 `BASE_TO_LIST_MAP` 形式暴露给推断流程）；`upgrade_to_list_type` 作为唯一的“标量→列表”提升入口，所有在“声明为列表类/泛型列表”前提下从值/连线/泛型派生列表类型的场景都应经由该函数完成映射，避免在各处直接维护平行映射表；同时提供 `get_non_empty_str` / `is_non_empty_str` 这类字符串判空辅助函数与 `unique_preserve_order` / `pick_first_unique` 等“顺序去重”小工具，统一类型名处理与候选集合收敛逻辑。
  - `port_type_context.py`：端口类型推断所需的图上下文工具，负责为 `GraphModel` 构建入/出边索引，并基于边集合签名在 `GraphModel` 实例上缓存 `EdgeLookup`，内部的入/出边遍历辅助函数通过统一实现维护，避免在“有无 EdgeLookup 缓存”两种路径上复制粘贴逻辑；同时标准化 `metadata['port_type_overrides']` 结构并提供 `normalize_node_id_for_overrides`/`get_node_port_type_overrides_for_id`/`resolve_port_type_with_overrides` 等工具，用于兼容 copy_block 节点 ID 与统一解释覆盖表中的端口类型（只接受非空、非泛型、非流程类型的覆盖值）。
  - `port_type_generics.py`：围绕“泛型家族”与普通数据端口的类型推断工具集，在不抛异常的前提下从节点定义读取端口声明类型，并结合输入常量、上游入/出边以及覆盖表推断输入/输出端口的具体数据类型；覆盖表解析统一委托 `port_type_context.resolve_port_type_with_overrides`，与“有效输出类型”推断共用一套规则，内部统一通过字符串辅助函数规范化类型名，避免在各处散落 `isinstance(..., str) and x.strip()` 判断。
  - `port_type_dicts.py`：字典端口与别名字典类型的键/值推断工具，别名字典解析规则（`parse_typed_dict_alias`）统一复用 `engine/type_registry.py`，避免自动化侧与引擎侧出现不同的“字典别名格式”漂移；并基于入边与覆盖表为字典输入端口计算键/值类型，候选组合按“首次出现顺序去重”收敛，供自动化端口类型设置与 Todo UI 复用。
  - `port_type_inference.py`：端口类型推断门面模块，向外统一导出通用类型工具、上下文工具、泛型推断与字典推断函数，保持 `app.automation.ports.port_type_inference` 这一导入路径的稳定性；公共符号列表通过聚合子模块的 `__all__` 并经顺序去重得到，确保导出顺序稳定、行为一致。
  - `vector3_axis_detection.py` / `vector3_click_strategy.py` / `vector3_ui_apply.py`：三维向量端口的轴标签识别、点击几何策略与 UI 应用层工具，分别负责 OCR 文本清洗与 X/Y/Z 轴 bbox 补全、基于标签或 Warning/端口位置推导各轴点击中心，以及高亮标注和点击+文本注入等 UI 细节；轴级点击与文本输入通过 `vector3_ui_apply.apply_vector3_plan` 统一封装，三条轴共用同一套“可视化圆点/矩形 + 点击 + `_input_text_with_hooks` + 缓冲等待”流程。
  - `vector3_input_handler.py`：三维向量端口输入编排入口，围绕 OCR 路径与几何路径调用上述子模块完成三维向量分量的点击与文本注入，并将通用的日志/可视化/暂停钩子经 `AutomationStepContext` 传入 `apply_vector3_plan`，保持对外导入路径与内部执行节奏稳定。
- `port_type_steps.py` 复用 `app.automation.editor.node_snapshot.NodePortsSnapshotCache`，输入/输出侧共用统一的节点截图与端口列表缓存，脏标记由核心工具维护，减少重复 OCR，并在类型推断阶段复用预构建的入/出边索引（`build_edge_lookup`），避免在每个端口上重复全图遍历；同时通过 `port_type_effective` / `port_type_ui_core` / `port_type_ui_steps` / `port_type_steps_common` / `port_type_steps_input` / `port_type_steps_output` 等子模块，将“有效类型推断 / 端口类型设置 UI 原语 / 端口定位与通用 UI 步骤 / 输入/输出侧流程”拆分为互相协作的独立层次；端口定位与 Settings 行选择均基于调用方显式提供的端口列表工作，如需在鼠标移出节点后重试端口识别，则由上层注入端口枚举函数并通过参数传入；输入侧类型设置会严格按照 Todo 步骤中给出的参数名集合筛选要处理的端口，避免在步骤未声明的输入端口上额外尝试设置类型（例如未列出的字典输入端口），输出侧则继续按“所有泛型/未声明/动态类型的数据输出端口”遍历并结合覆盖表与连线推断目标类型；通用端口类型推断工具会集中在 `port_type_common.py` 与 `port_type_generics.py` 中维护，包括基础/列表类型映射、列表类类型名判定、类型名规范化与候选类型集合的顺序去重/首选策略，供 `port_type_effective` 和 UI 适配层统一复用。
- `_struct_field_types.py`：基于 `engine.resources.definition_schema_view` 为所有结构体字段构建“字段名 → 规范类型名”的只读映射，当同名字段在不同结构体中的类型不一致时，该字段映射为空字符串表示类型不确定；公共入口 `lookup_struct_field_type_by_name` 通过 `port_type_inference` 重新导出，供自动化执行与 Todo UI 的类型推断共用。
- `port_type_steps_common.py`：封装输入/输出侧复用的端口遍历与类型设置 UI 骨架（在已有快照上按端口名定位中心并调用具体设置回调），统一 `typed_side_once` 与“首个数据端口复用当前帧快照”的策略，避免在各侧单独维护重复逻辑。
- `port_type_setter.py` 与 `config.settings_scanner` 共用 `app.automation.editor.node_snapshot.capture_node_ports_snapshot`，确保截图/端口枚举逻辑一致且只做一次；`execute_set_port_types_merged` 仅作为编排入口，实际步骤拆分为“节点上下文准备（prepare_node_context）/端口可视化（emit_overlays）/输入端口类型设置（set_input_types）/输出端口类型设置（set_output_types）”四个子过程。
- 端口类型/向量输入等模块中的缓冲等待统一委托 `_exec_utils.log_wait_if_needed()`（包括字典类型设置弹窗与键/值类型选择阶段），以便在执行器开启 `fast_chain_mode` 时自动跳过；当上层提供暂停/终止钩子时，该等待也会按固定间隔轮询钩子，避免长时间 sleep 阻塞用户控制。

## 注意事项
- 端口种类/方向等判定统一走本目录的工具函数，避免在其他模块中复制粘贴类似逻辑。
- 与视觉识别相关的接口（如 list_ports）由 `app.automation.vision` 提供，这里仅在其结果之上进行逻辑处理；本目录中的函数不会直接调用视觉识别，而是通过端口识别快照或上层注入的端口枚举函数获取端口列表。
- 在新增端口相关能力时，优先考虑复用或扩展已有的类型推断与结构定义，避免引入平行体系。
- 端口类型覆盖信息统一通过 `GraphModel.metadata['port_type_overrides']` 提供，并由 `build_port_type_overrides` 负责标准化为 `{node_id: {port_name: type_text}}` 结构；标准化结果会缓存在 `GraphModel` 实例上以避免在多次推断中重复扫描 metadata，在类型推断阶段会优先读取覆盖表。对于通过复制块产生的节点（ID 以 `_copy_block_` 结尾），类型推断会自动按“去掉 copy_block 后缀”的原始节点 ID 查找覆盖项，保证同一逻辑节点在不同拷贝上获得一致的端口类型。
- 端口类型推断相关的公共 API 对外统一由 `port_type_inference.py` 暴露；`app.automation.ports` 以外的模块禁止直接从 `port_type_common`、`port_type_context`、`port_type_generics`、`port_type_dicts` 等子模块导入，以保证内部实现可以自由重构而不影响入口层导入路径。

- Settings 行中 kind 为 Settings 的端口筛选逻辑集中在 `settings_locator.py` 内部工具函数中实现，避免在其他模块中重复编写相同判断。

### `port_type_ui_core.py` 与 `port_type_ui_steps.py` 细节
- `port_type_ui_core.py`：收敛“点击 Settings 图标 → 打开类型搜索对话框 → 在搜索框内选择类型”的基础 UI 原语，统一处理模板/识别回退逻辑与泛型类型防护，并通过 `apply_type_in_open_search_dialog` 与 `set_port_type_with_settings` 两个函数对上层暴露；两者均通过 `AutomationStepContext` 接收 `log_callback` / `visual_callback` / `pause_hook` / `allow_continue` 等运行时上下文，避免在函数签名中重复列出相同参数组合；类型搜索入口统一基于字符串判空辅助函数，避免在 UI 层重复编写空字符串判断。
- `port_type_ui_steps.py`：在 `port_type_ui_core` 提供的原语之上，封装端口中心定位与“通用类型设置”流程（`apply_port_type_via_ui`）；当目标类型解析为“别名字典”（如 `键类型_值类型字典` 或 `键类型-值类型字典`）时，会自动委托 `dict_port_type_steps.set_dict_port_type_with_settings` 走 Dictionary 对话框的键/值设置流程，其余情况则直接通过 Settings 设置单一类型字符串；调用端仅需计算最终类型文本（含字典别名）并构造一次 `AutomationStepContext`，便可在整条端口类型设置链路中复用日志与暂停钩子配置。

### `port_picker.py` 细节
- 提供端口中心定位与 Settings 行识别能力，覆盖命名/序号/索引/几何等多级回退策略；端口筛选统一经 `filter_screen_port_candidates` 做侧别与可连接性过滤，再按期望 kind 与序号策略分层筛选，kind 语义通过 `_ports.get_port_category()` 映射为“数据/流程输入输出”等高层类别。
- 端口选择优先级：精确命名 → 序号（`ordinal_fallback_index`）→ 数字端口名顺序 → 索引推断 → 默认首个符合侧向与类型的候选。
- Settings 行识别：优先 `kind == 'settings'` 的候选；若存在置信度（confidence）字段则仅在 `confidence >= 0.8` 的候选中按行中心垂直距离与横向位置选择最近一行，若全为低置信度则视为一步式识别失败交由调用方回退模板搜索；未标注 Settings 时选行内最外侧的对应方向元素，仍失败时再做模板搜索；行内元素所在行的粗筛选与横向几何约束由 `settings_locator.py` 负责，均基于 `_ports.get_port_center_*()` 与 `_ports.get_port_category()`。
- 侧向约束：右侧以节点宽度 60% 以右为候选，左侧以节点宽度 40% 以内为候选；行内元素优先同侧匹配。
- 端口挑选顺序：先按端口名称精确命中，其次依据节点定义的 index（识别阶段提供）排序回退，避免仅靠物理位置导致有限循环等节点的多流程入口误判；最终再落入序号/索引/首项回退。
- 失败处理：返回 (0, 0) 交由调用方决定回退策略；保持日志输出与历史实现一致，不做异常吞噬。
- 端口类型设置流程复用同一帧截图/端口识别结果（脏标记刷新），在 `port_type_steps_input/output` 中按侧别遍历端口时，避免在多端口场景下每一步都重新截图与 OCR。
- 类型推断阶段若值推断得到“字符串/字符串列表”但存在连线可提供更具体的非泛型类型，则统一由 `port_type_effective` 按规则采用连线信息覆盖；若完全无法推断出具体类型，则返回空字符串并由输入/输出侧步骤跳过该端口的类型设置，避免无意义的“默认字符串”回退。


