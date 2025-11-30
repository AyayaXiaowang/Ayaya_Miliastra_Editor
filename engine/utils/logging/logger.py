from __future__ import annotations

from datetime import datetime
from typing import Any

_settings = None  # 延迟导入 settings，避免循环依赖


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _get_settings():
    """
    延迟获取全局设置实例。
    
    这样可以避免在导入阶段形成 `settings ↔ logger` 的循环依赖，
    同时保持对 `settings.NODE_IMPL_LOG_VERBOSE` 的兼容使用。
    """
    global _settings
    if _settings is None:
        from engine.configs.settings import settings as _settings_instance

        _settings = _settings_instance
    return _settings


def log_info(message: str, *args: Any) -> None:
    """信息日志。由 settings.NODE_IMPL_LOG_VERBOSE 控制是否输出。"""
    settings = _get_settings()
    if getattr(settings, "NODE_IMPL_LOG_VERBOSE", False):
        if args:
            print(f"[INFO { _now() }] " + message.format(*args))
        else:
            print(f"[INFO { _now() }] {message}")


def log_warn(message: str, *args: Any) -> None:
    """警告日志。始终输出。"""
    if args:
        print(f"[WARN { _now() }] " + message.format(*args))
    else:
        print(f"[WARN { _now() }] {message}")


def log_error(message: str, *args: Any) -> None:
    """错误日志。始终输出。"""
    if args:
        print(f"[ERR  { _now() }] " + message.format(*args))
    else:
        print(f"[ERR  { _now() }] {message}")



