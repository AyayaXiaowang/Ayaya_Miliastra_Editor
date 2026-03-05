## 目录用途
实体域配置数据与枚举（纯数据）：玩家/角色/造物/物件等实体结构、配置侧规则集、模型清单等，供编辑器、校验与运行时共享引用。

## 当前状态
- 以 `dataclass` 为主；关键模块包括 `entity_configs.py`、`profession_config.py`、`skill_config.py`、`revival_config.py`、`creature_models.py`、`entity_rules_complete.py`。
- 与 `engine.validate.entity_config_validator` 联动，用于静态校验实体配置合法性。

## 注意事项
- 实体说明保持概念层描述，不硬编码外部文档/知识库的物理路径或 URL。
- 跨模块引用优先复用权威定义，避免重复枚举/字段口径漂移。
- 不使用 `try/except` 吞错；异常结构应直接抛错暴露问题。

