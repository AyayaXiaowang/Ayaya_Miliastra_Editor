from __future__ import annotations

"""
Integrations package.

用于收拢与外部系统/宿主工程的适配：
- Graph_Generater 的类型体系、校验入口等（避免直接 import engine/__init__ 的副作用）
- runtime cache / BeyondLocal 路径 / 外部转换器等

目标：让纯“域内规则/语义”尽量不依赖这些适配层。
"""

