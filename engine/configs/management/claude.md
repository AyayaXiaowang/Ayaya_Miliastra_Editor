## 目录用途
管理/系统层配置数据模型（纯数据）：镜头与路径、计时器与变量、关卡设置、商店经济、音频、存档点、外围系统等，为编辑器、校验与工具链提供统一结构。

## 当前状态
- 配置按子域拆分为多个 `*_configs.py` 模块，整体以 `dataclass` 为主；对外入口为 `engine.configs.management`。
- 常用模块示例：`camera_and_path_configs.py`、`timer_variable_configs.py`、`level_settings_configs.py`、`shop_economy_configs.py`、`audio_music_configs.py`、`ingame_save_config.py`。

## 注意事项
- 仅承载字段与序列化逻辑，不写业务流程；字段默认值/范围应可被校验器消费。
- 避免在说明中写外部文档/知识库的物理路径或 URL，仅保留概念性描述。
- 保持命名语义清晰，避免缩写；不使用 `try/except` 吞错。

