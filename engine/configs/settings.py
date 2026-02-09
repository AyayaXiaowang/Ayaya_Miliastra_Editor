"""全局设置模块 - 控制程序行为和调试选项

这个模块提供了一个集中的配置系统，用于控制程序的各种行为。
支持从配置文件加载和保存设置，并提供UI界面进行设置。

使用方法：
    from engine.configs.settings import settings
    from engine.utils.logging.logger import log_info
    
    if settings.LAYOUT_DEBUG_PRINT:
        log_info("调试信息")
    
    # 保存设置
    settings.save()
    
    # 加载设置
    settings.load()
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from engine.utils.logging.logger import log_info, log_warn

DEFAULT_USER_SETTINGS_RELATIVE_PATH = Path("app/runtime/cache/user_settings.json")


class Settings:
    """全局设置类
    
    所有设置项都是类属性，可以直接访问和修改。
    """
    
    # ========== 调试选项 ==========
    
    # 是否在布局时打印详细的调试信息
    # 设置为 True 会在自动排版时打印节点排序、位置计算等详细信息
    # 默认 False（关闭），减少控制台输出
    LAYOUT_DEBUG_PRINT: bool = False
    
    # 是否在节点定义加载时打印详细日志
    # 默认 False，只在明确需要时才打开
    # ⚠️ 需要重启程序才能生效
    NODE_LOADING_VERBOSE: bool = False

    # 是否将别名键注入到节点定义库
    # True：为每个别名在库中注册一份"类别/别名"的直达键（兼容旧调用）
    # False：仅通过 V2 索引（NodeLibrary.get_by_alias）解析别名，库内不注入别名条目
    NODE_ALIAS_INJECT_IN_LIBRARY: bool = True

    # 节点加载管线已统一为 V2（pipeline/）唯一实现；不再提供切换开关
    
    # 图编辑UI详细日志（端口布局/连线创建等）
    # 默认 False，避免打开节点图时在控制台大量输出
    GRAPH_UI_VERBOSE: bool = False

    # TwoRowField 表格行高调试打印（[UI调试/TwoRowField]）
    # 默认 False（关闭），用于排查两行结构字段表格的 sizeHint/行高对齐问题时再开启
    UI_TWO_ROW_FIELD_DEBUG_PRINT: bool = False

    # UI预览日志详细输出（[PREVIEW] 标签）
    # 默认 False，避免启动或普通操作时刷屏
    PREVIEW_VERBOSE: bool = False
    
    # ========== 验证选项 ==========
    
    # 验证器详细模式（用于调试验证逻辑）
    # 默认 False
    VALIDATOR_VERBOSE: bool = False

    # 节点图运行时代码校验（类结构脚本）：
    # 说明：`engine.validate.node_graph_validator.validate_node_graph` 当前会无条件触发一次性文件级校验，
    # 以确保不支持语法/非法节点调用在“运行/导入节点图脚本”阶段立即暴露；
    # 本开关主要保留为兼容与未来扩展（例如某些入口是否自动注入校验钩子）。
    RUNTIME_NODE_GRAPH_VALIDATION_ENABLED: bool = True

    # 节点图验证：是否启用"实体入参仅允许连线/事件参数"的严格模式
    # False：默认模式，仅禁止文本/常量；允许变量/属性（如 self.owner_entity）
    # True：严格模式，仅允许节点输出（连线）或事件参数；不允许任意属性/局部常量
    STRICT_ENTITY_INPUTS_WIRE_ONLY: bool = False
    
    # ========== 其他选项 ==========
    
    # 是否在启动时跳过安全声明弹窗
    # False：每次启动都会弹出安全声明；True：不再提示
    SAFETY_NOTICE_SUPPRESSED: bool = False
    
    # 节点实现层日志：控制 `engine.utils.logging.logger.log_info` 是否输出
    # 默认 False（关闭），生产环境下仅保留 warn/error
    NODE_IMPL_LOG_VERBOSE: bool = False

    # 调试日志：控制 `engine.utils.logging.logger.log_debug` 是否输出
    # 默认 False，避免启动或普通操作时刷屏
    DEBUG_LOG_VERBOSE: bool = False

    # 是否在 UI 全局未捕获异常时弹出阻塞错误对话框（QMessageBox）。
    # 默认 False：避免“任何错误都弹窗”打断操作；异常仍会输出到控制台/日志并落盘到运行时缓存。
    UI_UNHANDLED_EXCEPTION_DIALOG_ENABLED: bool = False

    # ========== 全局性能监控（UI 卡顿定位） ==========
    #
    # 设计目标：
    # - 当用户“感觉卡顿”时，直接在 UI 内看到：卡了多久、卡在什么调用栈；
    # - 监控默认关闭：避免日常使用的额外开销与噪音；
    # - 监控基于“UI 心跳 + 后台 watchdog 采样主线程堆栈”实现：当事件循环阻塞超过阈值时记录一次卡顿事件。
    #
    # 开启后会记录卡顿事件与少量命名耗时段（若上层有插桩），并可通过全局悬浮面板/详情面板查看。
    APP_PERF_MONITOR_ENABLED: bool = False
    # 在主窗口显示“性能悬浮面板”（全页面可见，点击可打开详情面板）。
    APP_PERF_OVERLAY_ENABLED: bool = False
    # 卡顿判定阈值（毫秒）。一般建议 >=200ms，过低可能因正常调度抖动产生误报。
    APP_PERF_STALL_THRESHOLD_MS: int = 250
    # 是否在卡顿期间采样主线程调用栈（用于定位“到底卡在哪里”）。
    APP_PERF_CAPTURE_STACKS_ENABLED: bool = True
    
    # 自动保存间隔（秒），0 表示每次修改都立即保存
    AUTO_SAVE_INTERVAL: float = 0.0
    
    # 是否在节点图代码解析时打印详细信息
    GRAPH_PARSER_VERBOSE: bool = False
    
    # 是否在节点图代码生成时打印详细信息
    # 设置为 True 会在生成代码时打印事件流分析、拓扑排序等详细信息
    # 默认 False（关闭），减少控制台输出
    GRAPH_GENERATOR_VERBOSE: bool = False

    # 节点图 `.gia` 导出：节点坐标缩放倍数（展示用，不影响图逻辑语义）
    #
    # 说明：
    # - GraphModel(JSON) 的 node.payload.pos 为 Graph_Generater 画布坐标系；
    # - 导出 `.gia` 时会对 x/y 同步乘以该系数，再做一次 X 轴居中偏移；
    # - 默认 2.0 为历史经验值：不缩放时在真源编辑器中更容易显得“过于紧凑”（节点/连线更拥挤）。
    #
    # 取值建议：0.1 ~ 200.0（过大可能导致坐标过远，导入后需要频繁缩放/平移查看）
    UGC_GIA_NODE_POS_SCALE: float = 2.0
    
    # 界面主题模式：
    # - "auto"：跟随系统浅色/深色（默认）
    # - "light"：始终使用浅色主题
    # - "dark"：始终使用深色主题
    UI_THEME_MODE: str = "auto"

    # 资源库自动刷新开关：
    # True：当 `assets/资源库` 下的资源被外部工具修改时，文件监控会自动检测并刷新资源索引与相关视图；
    # False：关闭自动刷新，仅在用户点击主窗口工具栏的“更新”按钮或通过其它入口显式触发时才刷新资源库。
    RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED: bool = True

    # 运行时缓存根目录（相对于 workspace 的路径，或绝对路径）。
    # 默认 "app/runtime/cache"。
    #
    # 说明：
    # - 引擎层通过 `engine.utils.cache.cache_paths.get_runtime_cache_root()` 统一派生各类缓存路径；
    # - 当需要将缓存挪出仓库目录（例如放到更快的磁盘/临时目录）时，可修改该值。
    RUNTIME_CACHE_ROOT: str = "app/runtime/cache"

    # ========== 私有扩展 ==========
    # 说明：
    # - 公开仓库只提供“扩展点 + 加载机制”，私有实现由使用者在本机配置并加载；
    # - 配置值会写入用户设置文件 `app/runtime/cache/user_settings.json`（默认在 .gitignore 内），不会进入仓库。
    #
    # 启用方式：
    # - PRIVATE_EXTENSION_ENABLED 当前会被强制为 True（不再在设置页中展示开关）；
    # - 若想“放进工作区即可自动加载”：把插件放在 `<workspace_root>/private_extensions/<插件名>/plugin.py`（推荐）；
    #   - 兼容：也支持 `<workspace_root>/plugins/private_extensions/<插件名>/plugin.py`；
    # - 若想加载工作区外的私有包：配置 PRIVATE_EXTENSION_SYS_PATHS / PRIVATE_EXTENSION_MODULES；
    # - 或使用环境变量覆盖（见 app.common.private_extension_loader 的说明）。
    PRIVATE_EXTENSION_ENABLED: bool = True
    PRIVATE_EXTENSION_SYS_PATHS: list[str] = []
    PRIVATE_EXTENSION_MODULES: list[str] = []
    
    # ========== 布局增强（默认关闭/中性） ==========
    # 纯数据图：层内排序策略
    # 可选： "none"（不排序，保持旧行为）、"out_degree"（出度降序）、"in_degree"（入度升序）、"hybrid"（出度降序+入度升序）
    # 默认 "none"
    LAYOUT_DATA_LAYER_SORT: str = "none"
    # 几何插空策略：为保证"数据位于生产者与消费者流程节点之间"而对流程槽位右侧插入空槽
    # 默认 False（关闭，保持旧行为）
    LAYOUT_ENABLE_GEOMETRIC_SLOT: bool = False
    # 节点类型严格模式：流程输出仅由标准规则判定（端口名），不再将"多分支"节点的所有输出视作流程口
    # 默认 False（关闭，行为与之前版本等价）
    LAYOUT_STRICT_NODE_KIND: bool = False
    # 块间紧凑排列：在列内堆叠阶段满足端口/碰撞约束后，是否继续向左贴近上游块
    # True：尽量把块往左移动（默认行为）；False：保留列左边界，不额外左移
    LAYOUT_TIGHT_BLOCK_PACKING: bool = True

    # ========== 自动排版间距（倍率，百分比） ==========
    # 自动排版时相邻节点之间的基础间距倍率（横向/纵向，单位：%）。
    # - 100：保持当前默认间距（基准）
    # - 200：在当前基础间距上放大到 2 倍
    #
    # 说明：
    # - 该倍率仅影响布局算法内部使用的“间距常量”（如列间距、块间距、堆叠间距等）；
    # - 不改变节点的宽高估算与端口行高，只调节相邻节点矩形之间的空隙。
    LAYOUT_NODE_SPACING_X_PERCENT: int = 100
    LAYOUT_NODE_SPACING_Y_PERCENT: int = 100

    # 块内数据节点Y紧凑偏好：
    # 背景：块内数据节点的 Y 位置除了受“端口Y下界/列底不重叠/多父合流区间”等硬约束影响，
    # 还会在 `DataYRelaxationEngine` 中被“邻居居中/分叉居中”目标拉扯，极端情况下会形成较大的垂直空洞。
    #
    # 本开关用于在满足硬约束的前提下，引入“向上压紧”的偏好：
    # - 当某节点相对其硬下界（端口/流程底部）存在较大可上移余量时，会把松弛目标向下界方向拉近；
    # - 这会让可调整的父级链条整体更靠近上方区域，从而让合流子节点也更紧凑。
    #
    # True：启用（默认）；False：关闭，保持更“居中”的旧观感。
    LAYOUT_COMPACT_DATA_Y_IN_BLOCK: bool = True
    # 紧凑拉近系数（0~1）：
    # - 0：强制尽量贴近下界（更紧凑，但更可能牺牲“居中”观感）
    # - 1：不做紧凑拉近（等价于关闭紧凑偏好）
    LAYOUT_DATA_Y_COMPACT_PULL: float = 0.6
    # 触发紧凑拉近的“可上移余量阈值”（像素）：
    # 只有当 (preferred_top_y - lower_bound_top_y) 大于该值时才会拉近，避免对本来就很紧凑的列产生抖动。
    LAYOUT_DATA_Y_COMPACT_SLACK_THRESHOLD: float = 200.0
    
    # 数据节点跨块复制：当数据节点被多个块共享时，是否为每个块创建真实副本
    # True：启用复制，每个块拥有独立的数据节点副本（副本真实存在，参与布局和执行）
    # False：保持现有逻辑（跨块跳过，数据节点只属于第一个块）
    # 默认 True（开启）
    DATA_NODE_CROSS_BLOCK_COPY: bool = True

    # 长连线自动生成“局部变量中转节点”（默认关闭）：
    # 背景：当同一基本块内存在“跨越很多流程节点”的数据边（例如 A→...→Y），连线会非常长；
    # 启用后，会在“跨块复制完成后、块内排版前”自动插入【获取局部变量】节点作为中转，
    # 将一条长边拆成多段较短的边，并让该节点参与后续排版与任务清单生成。
    #
    # 约束：仅在节点库中的【获取局部变量】具备 “初始值→值” 透传端口形态时启用；
    # 同时会尊重该节点对泛型类型的约束（例如禁止字典类型）。
    LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY: bool = False
    # 单段允许的最大“节点跨度”（范围：3~10；默认 5）。超过该跨度会自动插入中转节点拆分。
    LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE: int = 5

    # 布局算法版本号：当跨块复制或块归属等布局语义发生不兼容变更时递增，
    # 用于让旧的 graph_cache 在加载节点图时失效并触发重新解析与自动布局。
    LAYOUT_ALGO_VERSION: int = 2
    
    # ========== 布局性能优化（方案C + D）==========
    
    # 方案C：链枚举限流参数（防止指数爆炸）
    # 每个数据节点最多保留多少条链（超过则截断，保留代表性路径）
    # 默认 32（适中），设为 0 表示不限制
    LAYOUT_MAX_CHAINS_PER_NODE: int = 32
    
    # 端口公平策略：每个输入端口至少保留多少条代表性路径（在单节点上限内先满足该配额）
    # 默认 1，设为 0 表示不启用端口公平配额
    LAYOUT_MIN_PATHS_PER_INPUT: int = 1
    
    # 单个起点最多枚举多少条链（超过则早停）
    # 默认 512（较宽松），设为 0 表示不限制
    LAYOUT_MAX_CHAINS_PER_START: int = 512
    
    # 方案D：调试输出限流参数（降低日志噪音）
    # Y轴调试信息中，每个数据节点最多显示多少个端口明细
    # 默认 5，设为 0 表示不限制
    LAYOUT_DEBUG_MAX_PORTS: int = 5

    # ========== 基本块可视化选项 ==========
    
    # 是否显示基本块矩形框（半透明背景）
    # 基本块是从一个非分支节点开始，到下一个分支节点为止的连续节点序列
    # 默认 True（显示）
    SHOW_BASIC_BLOCKS: bool = True
    
    # 基本块矩形框的透明度（0.0-1.0）
    # 值越小越透明，建议范围 0.15-0.25
    # 默认 0.2
    BASIC_BLOCK_ALPHA: float = 0.2
    
    # 是否在节点旁显示"布局Y坐标分配逻辑"的调试叠加文本（前景层，描边文字）
    # 默认 False（关闭）
    SHOW_LAYOUT_Y_DEBUG: bool = False

    # ========== 节点图画布显示 ==========

    # 节点内容区背景的不透明度（0.0-1.0）。
    # 数值越大越不透明（越难透过节点看到后面的网格/内容）。
    # 默认 0.7：保持当前“节点半透明有底色”的观感。
    GRAPH_NODE_CONTENT_ALPHA: float = 0.7

    # 节点图画布：性能面板（用于定位拖拽/缩放/重绘卡顿来源）。
    # 默认 False（关闭）：避免在正常使用中引入额外统计开销。
    # 开启后会在画布左上角显示每帧耗时分解（scene绘制/网格/叠层/小地图/控件定位等）。
    GRAPH_PERF_PANEL_ENABLED: bool = False

    # 节点图画布：运行期 GraphScene LRU 缓存容量（同一次程序运行期内切图秒切回）。
    #
    # 说明：
    # - 用于 A→B→A 这类短时切换场景复用 QGraphicsItem，避免反复装配导致卡顿；
    # - 仅在同一进程内生效；跨重启无法复用 Qt 图元对象；
    # - 缓存会占用显著内存（QGraphicsItem 很重），建议保持很小（1~2）。
    #
    # 取值：
    # - 0：禁用（每次切图都重建画布）
    # - 1~N：最多缓存 N 张“非激活节点图”的画布
    GRAPH_SCENE_LRU_CACHE_SIZE: int = 2

    # 节点图画布：行内常量控件虚拟化（推荐）。
    #
    # 设计目标：
    # - 大图下最昂贵的对象通常是 QGraphicsProxyWidget（内嵌 QWidget 的布尔/向量等控件）；
    # - 开启后，节点默认只绘制“输入框外观 + 文本占位值”，仅在用户显式交互（点击/聚焦）时
    #   才临时创建真实控件，退出编辑后立即销毁，显著降低大图渲染与交互卡顿。
    #
    # 注意：该优化不等同于“快速预览模式”，不会压缩节点/连线，仅改变控件创建策略。
    GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED: bool = True

    # 节点图画布：超大图快速预览（压缩节点/连线，性能更好）。
    #
    # 说明：
    # - True：在“不可落盘会话（can_persist=False）且节点/连线数量超过阈值”时自动启用 fast_preview_mode，
    #   使用轻量 Node/Edge 图元（不创建端口与行内常量控件），并允许按节点展开查看详情；
    # - False：默认关闭，不自动进入“压缩预览”模式，始终使用完整图元渲染（更直观，但超大图可能更卡）。
    GRAPH_FAST_PREVIEW_ENABLED: bool = False
    # 快速预览触发阈值（仅在 GRAPH_FAST_PREVIEW_ENABLED=True 时生效）
    GRAPH_FAST_PREVIEW_NODE_THRESHOLD: int = 500
    GRAPH_FAST_PREVIEW_EDGE_THRESHOLD: int = 900
    # fast_preview_mode：批量绘制轻量预览边（进一步降低超大图的 QGraphicsItem 数量）。
    # - True：在 fast_preview_mode 下优先使用单一渲染层绘制所有“轻量预览边”，节点仍保持为 item；
    # - False：保持每条边一个 QGraphicsItem 的旧行为（更利于逐边调试，但超大图更卡）。
    GRAPH_FAST_PREVIEW_BATCHED_EDGES_ENABLED: bool = True

    # 只读大图：批量绘制连线（不启用 fast_preview 也可生效）。
    #
    # 设计目标：
    # - 典型场景：任务清单右侧节点图预览（只读，但需要保留节点完整信息与点击联动）；
    # - 节点仍保留为 item（NodeGraphicsItem），仅将连线从“每条边一个 EdgeGraphicsItem”
    #   收敛为“单一批量边渲染层 + 模型级命中/高亮/灰显状态”；
    # - 大幅降低超大图的 item 数量与重绘/命中开销。
    GRAPH_READONLY_BATCHED_EDGES_ENABLED: bool = True
    GRAPH_READONLY_BATCHED_EDGES_EDGE_THRESHOLD: int = 900

    # 节点图画布：是否启用“自动适配全图（fit_all）”的压缩视图行为。
    #
    # 说明：
    # - True：在进入编辑器/某些预览场景下会自动调用 `GraphView.fit_all()`，让全图一屏可见；
    # - False：默认关闭，不自动缩放到全图，避免超大图进入“压缩状态”且触发全量边界计算带来的卡顿。
    #
    # 提示：用户仍可通过快捷键（默认 Ctrl+0）手动触发适配全图。
    GRAPH_AUTO_FIT_ALL_ENABLED: bool = False

    # 节点图画布：缩放分级渲染（LOD，推荐）。
    #
    # 说明：
    # - True：在低倍率缩放（缩得很小时）自动隐藏端口标签/常量输入框等细节，并降低连线命中测试成本；
    #   目标是让“平移/缩放”在超大图下更顺滑，同时避免明显的模式切换割裂感。
    # - False：保持当前始终绘制全细节的行为（更直观，但超大图下更容易卡顿）。
    GRAPH_LOD_ENABLED: bool = True

    # LOD 阈值（场景缩放比例，1.0 为 100%）：
    # - 节点细节（端口标签/常量占位文本/验证感叹号等）显示阈值
    GRAPH_LOD_NODE_DETAILS_MIN_SCALE: float = 0.55
    # - 节点标题显示阈值（再小会跳过文字以减少绘制成本）
    GRAPH_LOD_NODE_TITLE_MIN_SCALE: float = 0.28
    # - 端口绘制阈值（过小时端口/虚拟引脚角标不绘制）
    GRAPH_LOD_PORT_MIN_SCALE: float = 0.30
    # - 连线绘制阈值（过小时仅绘制“选中/高亮链路”连线）
    GRAPH_LOD_EDGE_MIN_SCALE: float = 0.22
    # - 连线命中测试阈值（过小时非高亮/非选中连线返回空 shape，降低 hit-test 成本）
    GRAPH_LOD_EDGE_HITTEST_MIN_SCALE: float = 0.28

    # 画布网格：低倍率下的“最小像素间距”。
    # 当缩放导致网格线在屏幕像素上过密时，叠加层会自动放大 grid_size（例如 50→100→200），
    # 以降低背景绘制开销并避免噪音。
    GRAPH_GRID_MIN_PX: float = 12.0
    # 画布网格：是否绘制网格线（背景底色仍保留）。
    #
    # 说明：
    # - False：仅绘制纯底色，不绘制任何网格线，可显著降低超大图平移/缩放时的背景绘制开销。
    # - True：绘制细网格+粗网格（每 5 格一条粗线），用于增强空间感与对齐参照。
    GRAPH_GRID_ENABLED: bool = True

    # 节点图画布：平移/缩放期间隐藏小图标/端口等细节（提升流畅度）。
    #
    # 说明：
    # - True：平移（拖拽）或滚轮缩放期间临时隐藏端口圆点/⚙按钮/+按钮等小图元，并让叠加层跳过 YDebug 图标/链路徽标绘制；
    #   停止交互后按当前 LOD 状态恢复。目标是减少 Qt item 枚举与绘制的固定开销。
    # - False：平移/缩放期间不做该降级（画面更完整，但超大图更容易卡顿）。
    GRAPH_PAN_HIDE_ICONS_ENABLED: bool = True

    # 节点图画布：拖拽平移（手抓）期间“冻结为静态快照”（极致性能）。
    #
    # 说明：
    # - True：拖拽平移开始抓一张 viewport 像素快照，拖拽平移过程中只移动该快照并禁用视图更新，
    #   从而避免每帧重绘大量 QGraphicsItem（超大图平移更丝滑）。
    # - 代价：拖拽平移过程中画面是静态快照，不会显示新进入视口的节点/连线；松手后恢复真实渲染。
    #
    # 建议：
    # - 仅在“超大图平移卡顿明显”的场景开启；
    # - 或搭配小地图/适配全图使用以避免迷失方向。
    GRAPH_PAN_FREEZE_VIEWPORT_ENABLED: bool = False

    # 节点图画布：滚轮缩放期间“冻结为静态快照”（极致性能）。
    #
    # 说明：
    # - True：缩放开始抓一张 viewport 像素快照，滚轮缩放过程中仅对快照做缩放显示，并禁用视图更新，
    #   从而避免每步滚轮都重绘大量 QGraphicsItem；缩放停止后恢复真实渲染。
    # - 代价：缩放过程中画面是静态快照，不会显示新进入视口的节点/连线；停止滚轮后才会刷新真实内容。
    GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED: bool = False

    # LOD 可见性回滞阈值（避免在临界缩放附近频繁切换 setVisible 状态引发抖动）
    GRAPH_LOD_PORT_VISIBILITY_EXIT_SCALE: float = 0.33
    GRAPH_LOD_EDGE_VISIBILITY_EXIT_SCALE: float = 0.24

    # 块鸟瞰模式（仅显示 basic blocks，隐藏节点/连线图元）
    GRAPH_BLOCK_OVERVIEW_ENABLED: bool = True
    GRAPH_BLOCK_OVERVIEW_ENTER_SCALE: float = 0.10
    GRAPH_BLOCK_OVERVIEW_EXIT_SCALE: float = 0.12
    # 鸟瞰模式下网格最小像素间距（更大，避免低倍率噪音）
    GRAPH_BLOCK_OVERVIEW_GRID_MIN_PX: float = 24.0
    
    # ========== 任务清单选项 ==========
    
    # 是否合并连线步骤（简洁模式 vs 详细模式）
    # True: 合并同一对节点间的多条连线到一个步骤（默认，用户友好）
    # False: 每条连线生成独立步骤（用于自动化脚本或详细教程）
    TODO_MERGE_CONNECTION_STEPS: bool = True

    # 节点图步骤生成模式
    # - "human": 人类模式（保持现有逻辑，优先使用「连线并创建」）
    # - "ai": AI-先配置后连线（先生成创建节点 + 类型/参数配置步骤，最后统一生成连线步骤；不使用「连线并创建」）
    # - "ai_node_by_node": AI-逐个节点模式（逐个节点：创建→类型→参数；连线仍最后统一生成）
    TODO_GRAPH_STEP_MODE: str = "ai"

    # 任务清单：事件流根子步骤的 UI 加载策略
    # True：展开事件流根时按批次挂载子步骤（推荐，超大图更流畅，不阻塞 UI）
    # False：构建任务树时一次性创建事件流根的全部子步骤（更“完整”，但超大图可能明显卡顿）
    TODO_EVENT_FLOW_LAZY_LOAD_ENABLED: bool = False

    # ========== 真实执行 ==========
    # 真实执行调试日志（详细打印每一步识别、拖拽、验证信息）
    REAL_EXEC_VERBOSE: bool = False
    # 是否在每个真实执行步骤完成后，尝试在节点图画布上点击一次空白位置作为收尾
    # True：默认启用（推荐），可以关闭以完全保留旧行为并略微降低截图/识别开销
    REAL_EXEC_CLICK_BLANK_AFTER_STEP: bool = True

    # === 自动化回放记录（关键步骤 I/O 记录）===
    # 是否启用自动化“关键步骤输入输出记录”（JSONL + 可选截图），用于回归定位与离线复现。
    REAL_EXEC_REPLAY_RECORDING_ENABLED: bool = False
    # 是否在回放记录中额外落盘步骤前后截图（更直观，但有额外 IO 开销）。
    REAL_EXEC_REPLAY_CAPTURE_SCREENSHOTS: bool = False
    # 是否记录所有步骤（默认只记录计划表中标记为关键的步骤）。
    REAL_EXEC_REPLAY_RECORD_ALL_STEPS: bool = False
    
    # 鼠标执行模式：
    # "classic"：直接移动并点击/拖拽（保持最终光标在目标位置）
    # "hybrid"：瞬移到目标执行并在结束后复位到原始光标位置（更少打扰）
    MOUSE_EXECUTION_MODE: str = "classic"

    # 混合模式参数：拖拽轨迹分段步数与每步休眠（秒）
    MOUSE_HYBRID_STEPS: int = 40
    MOUSE_HYBRID_STEP_SLEEP: float = 0.008
    # 混合模式：释放后停留时间（秒），用于给UI处理点击/关闭列表的时间
    MOUSE_HYBRID_POST_RELEASE_SLEEP: float = 0.15
    # 拖拽策略："auto"（跟随 MOUSE_EXECUTION_MODE），"instant"（瞬移到终点），"stepped"（步进平滑）
    MOUSE_DRAG_MODE: str = "auto"

    # 文本输入方式：
    # "clipboard"：剪贴板 + Ctrl+V（对长文本稳定，依赖剪贴板）
    # "sendinput"：Windows SendInput UNICODE（更快，不卡剪贴板）
    TEXT_INPUT_METHOD: str = "clipboard"
    # 单个图步骤在真实执行中的最大自动重试次数（例如锚点回退后再次执行该步骤）。
    # 主要影响由任务清单触发的自动执行过程中的“出错后自动再试”次数上限。
    REAL_EXEC_MAX_STEP_RETRY: int = 3
    # OCR 候选列表相关的验证/触发最大重试轮数（如“候选列表是否关闭”的验证次数）。
    # 供自动化底层统一使用，避免各处硬编码不同的重试次数。
    REAL_EXEC_MAX_VERIFY_ATTEMPTS: int = 3
    
    # ========== 指纹消歧（重名邻域） ==========
    # 是否启用基于"邻域相对距离指纹"的重名消歧（仅影响识别几何拟合前的候选过滤）
    FINGERPRINT_ENABLED: bool = True
    # K 近邻数量（指纹长度约为 K-1），常用 8~12
    FINGERPRINT_K: int = 10
    # 指纹比例向量的小数位数（稳定性与区分度折中）
    FINGERPRINT_ROUND_DIGITS: int = 3
    # 指纹最大允许距离（L1，越小越严格），常用 0.18~0.25
    FINGERPRINT_MAX_DIST: float = 0.20
    # 指纹比较所需的最小重叠邻居数（防止证据过少导致的误判）
    FINGERPRINT_MIN_OVERLAP: int = 4
    # 是否输出指纹过滤的调试日志
    FINGERPRINT_DEBUG_LOG: bool = False
    
    # ========== 识别/几何拟合降级策略 ==========
    # 当几何拟合失败但画面存在"唯一标题（模型与场景均唯一）"时，是否允许降级放行：
    # - 行为：保留现有缩放（若无则使用默认缩放），仅以唯一标题集合估计平移项 origin 并更新映射；
    # - 风险：当缩放未知或偏差较大时，除该唯一节点外的其他位置可能存在较大误差，但可用于"先执行一步以便进入可见区域"的场景。
    UNIQUE_NODE_FALLBACK_ENABLED: bool = True
    # 当没有已有的 scale_ratio 可用时，降级路径使用的默认缩放
    UNIQUE_NODE_FALLBACK_DEFAULT_SCALE: float = 1.0
    
    # 配置文件路径（相对于workspace）
    _config_file: Optional[Path] = None
    # 工作区根目录（由 set_config_path(workspace_root) 显式注入）
    _workspace_root: Optional[Path] = None
    
    def __repr__(self) -> str:
        """返回所有设置的字符串表示"""
        settings_dict = {
            key: value for key, value in self.__class__.__dict__.items()
            if not key.startswith('_') and key.isupper()
        }
        return f"Settings({settings_dict})"
    
    @classmethod
    def set_config_path(cls, workspace_path: Path):
        """设置配置文件路径
        
        Args:
            workspace_path: 工作空间根目录
        """
        config_file = workspace_path / DEFAULT_USER_SETTINGS_RELATIVE_PATH

        # 约定：设置文件仅存放在运行期缓存目录（默认 app/runtime/cache/user_settings.json）。
        # 说明：这里不做任何“判空式容错”，文件系统错误应直接抛错暴露环境问题。

        log_info(
            "[BOOT][Settings] set_config_path: workspace_path={} -> config_file={}",
            workspace_path,
            config_file,
        )
        cls._config_file = config_file
        cls._workspace_root = workspace_path.resolve()
    
    def _get_all_settings(self) -> Dict[str, Any]:
        """获取所有设置项的字典
        
        注意：从实例获取属性，以支持实例属性覆盖类属性的情况
        """
        return {
            key: getattr(self, key)
            for key in dir(self.__class__)
            if not key.startswith('_') and key.isupper()
        }
    
    def save(self) -> bool:
        """保存设置到配置文件
        
        Returns:
            是否保存成功
        """
        if self.__class__._config_file is None:
            log_warn("⚠️  警告：配置文件路径未设置，无法保存设置")
            return False
        
        settings_dict = self._get_all_settings()
        
        # 确保目录存在
        self.__class__._config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存为JSON
        with open(self.__class__._config_file, 'w', encoding='utf-8') as file:
            json.dump(settings_dict, file, indent=2, ensure_ascii=False)
        
        return True
    
    def load(self) -> bool:
        """从配置文件加载设置
        
        Returns:
            是否加载成功
        """
        config_file = self.__class__._config_file
        if config_file is None:
            # 配置文件路径未设置，使用默认值
            log_info("[BOOT][Settings] load: _config_file 未设置，跳过加载，使用类默认值")
            return False
        
        if not config_file.exists():
            # 配置文件不存在，使用默认值
            log_info("[BOOT][Settings] load: 配置文件不存在（{}），跳过加载，使用类默认值", config_file)
            return False
        
        log_info("[BOOT][Settings] load: 准备从 {} 加载配置", config_file)
        with open(config_file, 'r', encoding='utf-8') as file:
            settings_dict = json.load(file)
        
        # 应用加载的设置到实例
        applied_count = 0
        for key, value in settings_dict.items():
            if hasattr(self.__class__, key) and key.isupper():
                setattr(self, key, value)
                applied_count += 1

        # 强制启用：不再由设置页控制
        # - 本地增强功能（私有扩展）：只在工作区存在插件/配置时才会产生实际效果。
        # - 资源库自动刷新：始终启用目录 watcher + 指纹确认链路，避免“外部修改后不刷新”的困惑。
        self.PRIVATE_EXTENSION_ENABLED = True
        self.RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED = True
        
        log_info("[BOOT][Settings] load: 配置加载完成，共应用 {} 个键", applied_count)
        return True
    
    @classmethod
    def reset_to_defaults(cls):
        """重置所有设置为默认值"""
        cls.LAYOUT_DEBUG_PRINT = False
        cls.NODE_LOADING_VERBOSE = False
        cls.UI_TWO_ROW_FIELD_DEBUG_PRINT = False
        cls.PREVIEW_VERBOSE = False
        cls.VALIDATOR_VERBOSE = False
        cls.RUNTIME_NODE_GRAPH_VALIDATION_ENABLED = False
        cls.AUTO_SAVE_INTERVAL = 0.0
        cls.GRAPH_PARSER_VERBOSE = False
        cls.GRAPH_GENERATOR_VERBOSE = False
        cls.UGC_GIA_NODE_POS_SCALE = 2.0
        cls.SAFETY_NOTICE_SUPPRESSED = False
        cls.UI_UNHANDLED_EXCEPTION_DIALOG_ENABLED = False
        cls.APP_PERF_MONITOR_ENABLED = False
        cls.APP_PERF_OVERLAY_ENABLED = False
        cls.APP_PERF_STALL_THRESHOLD_MS = 250
        cls.APP_PERF_CAPTURE_STACKS_ENABLED = True
        cls.RUNTIME_CACHE_ROOT = "app/runtime/cache"
        cls.RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED = True
        cls.PRIVATE_EXTENSION_ENABLED = True
        cls.PRIVATE_EXTENSION_SYS_PATHS = []
        cls.PRIVATE_EXTENSION_MODULES = []
        cls.LAYOUT_DATA_LAYER_SORT = "none"
        cls.LAYOUT_ENABLE_GEOMETRIC_SLOT = True
        cls.LAYOUT_STRICT_NODE_KIND = False
        cls.LAYOUT_TIGHT_BLOCK_PACKING = True
        cls.LAYOUT_NODE_SPACING_X_PERCENT = 100
        cls.LAYOUT_NODE_SPACING_Y_PERCENT = 100
        cls.DATA_NODE_CROSS_BLOCK_COPY = True
        cls.LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY = False
        cls.LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE = 5
        cls.SHOW_BASIC_BLOCKS = True
        cls.BASIC_BLOCK_ALPHA = 0.2
        cls.SHOW_LAYOUT_Y_DEBUG = False
        cls.GRAPH_NODE_CONTENT_ALPHA = 0.7
        cls.GRAPH_PERF_PANEL_ENABLED = False
        cls.GRAPH_SCENE_LRU_CACHE_SIZE = 2
        cls.GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED = True
        cls.GRAPH_FAST_PREVIEW_ENABLED = False
        cls.GRAPH_FAST_PREVIEW_NODE_THRESHOLD = 500
        cls.GRAPH_FAST_PREVIEW_EDGE_THRESHOLD = 900
        cls.GRAPH_FAST_PREVIEW_BATCHED_EDGES_ENABLED = True
        cls.GRAPH_READONLY_BATCHED_EDGES_ENABLED = True
        cls.GRAPH_READONLY_BATCHED_EDGES_EDGE_THRESHOLD = 900
        cls.GRAPH_AUTO_FIT_ALL_ENABLED = False
        cls.GRAPH_LOD_ENABLED = True
        cls.GRAPH_LOD_NODE_DETAILS_MIN_SCALE = 0.55
        cls.GRAPH_LOD_NODE_TITLE_MIN_SCALE = 0.28
        cls.GRAPH_LOD_PORT_MIN_SCALE = 0.30
        cls.GRAPH_LOD_EDGE_MIN_SCALE = 0.22
        cls.GRAPH_LOD_EDGE_HITTEST_MIN_SCALE = 0.28
        cls.GRAPH_GRID_MIN_PX = 12.0
        cls.GRAPH_GRID_ENABLED = True
        cls.GRAPH_PAN_HIDE_ICONS_ENABLED = True
        cls.GRAPH_PAN_FREEZE_VIEWPORT_ENABLED = False
        cls.GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED = False
        cls.GRAPH_LOD_PORT_VISIBILITY_EXIT_SCALE = 0.33
        cls.GRAPH_LOD_EDGE_VISIBILITY_EXIT_SCALE = 0.24
        cls.GRAPH_BLOCK_OVERVIEW_ENABLED = True
        cls.GRAPH_BLOCK_OVERVIEW_ENTER_SCALE = 0.10
        cls.GRAPH_BLOCK_OVERVIEW_EXIT_SCALE = 0.12
        cls.GRAPH_BLOCK_OVERVIEW_GRID_MIN_PX = 24.0
        cls.TODO_MERGE_CONNECTION_STEPS = True
        cls.TODO_GRAPH_STEP_MODE = "human"
        cls.TODO_EVENT_FLOW_LAZY_LOAD_ENABLED = True
        cls.REAL_EXEC_VERBOSE = False
        cls.REAL_EXEC_CLICK_BLANK_AFTER_STEP = True
        cls.REAL_EXEC_REPLAY_RECORDING_ENABLED = False
        cls.REAL_EXEC_REPLAY_CAPTURE_SCREENSHOTS = False
        cls.REAL_EXEC_REPLAY_RECORD_ALL_STEPS = False
        cls.MOUSE_EXECUTION_MODE = "classic"
        cls.MOUSE_HYBRID_STEPS = 40
        cls.MOUSE_HYBRID_STEP_SLEEP = 0.008
        cls.MOUSE_HYBRID_POST_RELEASE_SLEEP = 0.15
        cls.MOUSE_DRAG_MODE = "auto"
        cls.TEXT_INPUT_METHOD = "clipboard"
        cls.FINGERPRINT_ENABLED = True
        cls.FINGERPRINT_K = 10
        cls.FINGERPRINT_ROUND_DIGITS = 3
        cls.FINGERPRINT_MAX_DIST = 0.20
        cls.FINGERPRINT_MIN_OVERLAP = 4
        cls.FINGERPRINT_DEBUG_LOG = False
        log_info("✅ 已重置所有设置为默认值")
    
    @classmethod
    def enable_debug_mode(cls):
        """启用所有调试选项（用于开发调试）"""
        cls.LAYOUT_DEBUG_PRINT = True
        cls.NODE_LOADING_VERBOSE = True
        cls.UI_TWO_ROW_FIELD_DEBUG_PRINT = True
        cls.PREVIEW_VERBOSE = True
        cls.VALIDATOR_VERBOSE = True
        cls.GRAPH_PARSER_VERBOSE = True
        cls.GRAPH_GENERATOR_VERBOSE = True
        cls.RUNTIME_NODE_GRAPH_VALIDATION_ENABLED = True
        log_info("🔧 已启用调试模式：所有详细日志已打开")
    
    @classmethod
    def disable_debug_mode(cls):
        """禁用所有调试选项（恢复默认）"""
        cls.LAYOUT_DEBUG_PRINT = False
        cls.NODE_LOADING_VERBOSE = False
        cls.UI_TWO_ROW_FIELD_DEBUG_PRINT = False
        cls.PREVIEW_VERBOSE = False
        cls.VALIDATOR_VERBOSE = False
        cls.GRAPH_PARSER_VERBOSE = False
        cls.GRAPH_GENERATOR_VERBOSE = False
        cls.UI_THEME_MODE = "auto"
        log_info("✅ 已禁用调试模式：恢复默认设置")


# 全局设置实例
settings = Settings()

