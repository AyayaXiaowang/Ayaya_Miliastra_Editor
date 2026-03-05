from __future__ import annotations

from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.resources.resource_index_builder import ResourceIndexBuilder


def _write_text(target_file: Path, content: str) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content, encoding="utf-8")


def test_signal_and_struct_definition_py_files_are_indexed(tmp_path: Path) -> None:
    """
    回归：ResourceIndexBuilder 需要把 `管理配置/信号` 与 `管理配置/结构体定义` 视为
    代码级 Python 资源（.py），并递归扫描子目录。
    """
    workspace_path = tmp_path
    resource_library_dir = workspace_path / "assets" / "资源库"
    shared_root = resource_library_dir / "共享"

    signal_dir = shared_root / ResourceType.SIGNAL.value
    struct_dir = shared_root / ResourceType.STRUCT_DEFINITION.value / "基础结构体"

    signal_file = signal_dir / "demo_signal_file.py"
    struct_file = struct_dir / "demo_struct_file.py"
    ignored_signal_file = signal_dir / "校验信号.py"
    ignored_struct_file = struct_dir / "校验结构体定义.py"

    _write_text(
        signal_file,
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "SIGNAL_ID = 'signal_demo_01'",
                "SIGNAL_PAYLOAD = {'signal_id': SIGNAL_ID, 'signal_name': 'Demo', 'parameters': []}",
                "",
            ]
        ),
    )
    _write_text(
        struct_file,
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "STRUCT_ID = \"struct_demo_01\"",
                "STRUCT_TYPE = 'basic'",
                "STRUCT_PAYLOAD = {'type': 'Struct', 'struct_type': 'basic', 'struct_name': 'Demo', 'fields': []}",
                "",
            ]
        ),
    )
    # 同目录下允许存在“校验脚本”，索引扫描应忽略它们。
    _write_text(ignored_signal_file, "print('ignore')\n")
    _write_text(ignored_struct_file, "print('ignore')\n")

    builder = ResourceIndexBuilder(workspace_path, resource_library_dir)
    builder.build_index(lambda *args, **kwargs: False)
    cached = builder.try_load_from_cache()
    assert cached is not None, "索引缓存应在刚刚构建后立即可用"

    signal_bucket = cached.resource_index.get(ResourceType.SIGNAL, {})
    assert "signal_demo_01" in signal_bucket
    assert signal_bucket["signal_demo_01"].resolve() == signal_file.resolve()
    assert "校验信号" not in {path.stem for path in signal_bucket.values()}

    struct_bucket = cached.resource_index.get(ResourceType.STRUCT_DEFINITION, {})
    assert "struct_demo_01" in struct_bucket
    assert struct_bucket["struct_demo_01"].resolve() == struct_file.resolve()
    assert "校验结构体定义" not in {path.stem for path in struct_bucket.values()}


