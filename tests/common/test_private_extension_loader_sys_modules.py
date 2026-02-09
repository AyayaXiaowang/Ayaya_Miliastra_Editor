from __future__ import annotations

import sys
from pathlib import Path


def test_load_module_from_path_registers_sys_modules(tmp_path: Path, monkeypatch) -> None:
    """按文件路径加载模块时，必须先写入 sys.modules，避免 dataclasses/typing 依赖失败。

    复现点：
    - dataclasses 在处理 @dataclass 时会读取 sys.modules[cls.__module__].__dict__
    - 若 loader 未注册 sys.modules，会出现 AttributeError: 'NoneType' object has no attribute '__dict__'
    """
    from app.common import private_extension_loader as loader

    module_id = "tests._tmp_private_extension_for_sys_modules"
    monkeypatch.delitem(sys.modules, module_id, raising=False)

    plugin_py = tmp_path / "plugin.py"
    plugin_py.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "from dataclasses import dataclass",
                "",
                "@dataclass(frozen=True)",
                "class Demo:",
                "    x: int",
                "",
            ]
        ),
        encoding="utf-8",
    )

    module = loader._load_module_from_path(module_id=module_id, file_path=plugin_py)
    assert module_id in sys.modules
    assert sys.modules[module_id] is module
    assert hasattr(module, "Demo")


