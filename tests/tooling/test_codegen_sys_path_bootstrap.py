from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.codegen.composite_code_generator import CompositeCodeGenerator
from app.codegen.executable_code_generator import ExecutableCodeGenerator, ExecutableCodegenOptions


def test_executable_codegen_workspace_bootstrap_does_not_inject_app_dir() -> None:
    generator = ExecutableCodeGenerator(
        Path("."),
        node_library={},
        options=ExecutableCodegenOptions(import_mode="workspace_bootstrap", enable_auto_validate=False),
    )
    imports = generator._generate_executable_imports("server")
    generated = "\n".join(imports)

    assert "APP_DIR" not in generated
    assert "sys.path.insert(0, str(APP_DIR))" not in generated
    assert "sys.path.insert(0, str(PROJECT_ROOT))" in generated


def test_composite_codegen_does_not_inject_app_dir() -> None:
    generator = CompositeCodeGenerator(node_library={})
    dummy_composite = SimpleNamespace(scope="server")
    imports = generator._generate_imports(dummy_composite)
    generated = "\n".join(imports)

    assert "APP_DIR" not in generated
    assert "sys.path.insert(0, str(APP_DIR))" not in generated
    assert "sys.path.insert(0, str(PROJECT_ROOT))" in generated


