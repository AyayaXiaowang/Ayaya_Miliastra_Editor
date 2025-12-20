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

    # UI预览日志详细输出（[PREVIEW] 标签）
    # 默认 False，避免启动或普通操作时刷屏
    PREVIEW_VERBOSE: bool = False
    
    # ========== 验证选项 ==========
    
    # 验证器详细模式（用于调试验证逻辑）
    # 默认 False
    VALIDATOR_VERBOSE: bool = False

    # 节点图运行时代码校验（类结构脚本）：
    # False：默认关闭，仅依赖 CLI / 工具链在开发与构建阶段进行校验；
    # True：在节点图类被导入或实例化时触发一次性文件级校验（适合调试阶段快速发现问题）。
    RUNTIME_NODE_GRAPH_VALIDATION_ENABLED: bool = False

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
    
    # 自动保存间隔（秒），0 表示每次修改都立即保存
    AUTO_SAVE_INTERVAL: float = 0.0
    
    # 是否在节点图代码解析时打印详细信息
    GRAPH_PARSER_VERBOSE: bool = False
    
    # 是否在节点图代码生成时打印详细信息
    # 设置为 True 会在生成代码时打印事件流分析、拓扑排序等详细信息
    # 默认 False（关闭），减少控制台输出
    GRAPH_GENERATOR_VERBOSE: bool = False
    
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
    
    # ========== 任务清单选项 ==========
    
    # 是否合并连线步骤（简洁模式 vs 详细模式）
    # True: 合并同一对节点间的多条连线到一个步骤（默认，用户友好）
    # False: 每条连线生成独立步骤（用于自动化脚本或详细教程）
    TODO_MERGE_CONNECTION_STEPS: bool = True

    # 节点图步骤生成模式
    # "human": 人类模式（保持现有逻辑，优先使用「连线并创建」）
    # "ai": AI模式（先创建完所有节点，再逐个连接，不使用「连线并创建」）
    TODO_GRAPH_STEP_MODE: str = "ai"

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
        
        log_info("[BOOT][Settings] load: 配置加载完成，共应用 {} 个键", applied_count)
        return True
    
    @classmethod
    def reset_to_defaults(cls):
        """重置所有设置为默认值"""
        cls.LAYOUT_DEBUG_PRINT = False
        cls.NODE_LOADING_VERBOSE = False
        cls.PREVIEW_VERBOSE = False
        cls.VALIDATOR_VERBOSE = False
        cls.RUNTIME_NODE_GRAPH_VALIDATION_ENABLED = False
        cls.AUTO_SAVE_INTERVAL = 0.0
        cls.GRAPH_PARSER_VERBOSE = False
        cls.GRAPH_GENERATOR_VERBOSE = False
        cls.SAFETY_NOTICE_SUPPRESSED = False
        cls.RUNTIME_CACHE_ROOT = "app/runtime/cache"
        cls.LAYOUT_DATA_LAYER_SORT = "none"
        cls.LAYOUT_ENABLE_GEOMETRIC_SLOT = True
        cls.LAYOUT_STRICT_NODE_KIND = False
        cls.LAYOUT_TIGHT_BLOCK_PACKING = True
        cls.DATA_NODE_CROSS_BLOCK_COPY = True
        cls.SHOW_BASIC_BLOCKS = True
        cls.BASIC_BLOCK_ALPHA = 0.2
        cls.SHOW_LAYOUT_Y_DEBUG = False
        cls.TODO_MERGE_CONNECTION_STEPS = True
        cls.TODO_GRAPH_STEP_MODE = "human"
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
        cls.PREVIEW_VERBOSE = False
        cls.VALIDATOR_VERBOSE = False
        cls.GRAPH_PARSER_VERBOSE = False
        cls.GRAPH_GENERATOR_VERBOSE = False
        cls.UI_THEME_MODE = "auto"
        log_info("✅ 已禁用调试模式：恢复默认设置")


# 全局设置实例
settings = Settings()

