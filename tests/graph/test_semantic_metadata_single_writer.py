from __future__ import annotations

import ast
from pathlib import Path

from tests._helpers.project_paths import get_repo_root

from engine.graph.common import (
    SIGNAL_NAME_PORT_NAME,
    SIGNAL_SEND_NODE_TITLE,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_NAME_PORT_NAME,
)
from engine.graph.models.graph_model import GraphModel
from engine.graph.semantic import (
    GraphSemanticPass,
    SEMANTIC_SIGNAL_ID_CONSTANT_KEY,
    SEMANTIC_STRUCT_ID_CONSTANT_KEY,
)


def test_graph_semantic_pass_can_build_signal_bindings_from_signal_name_constant() -> None:
    from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
    from engine.signal import get_default_signal_repository, invalidate_default_signal_repository_cache
    from engine.utils.runtime_scope import set_active_package_id

    # 信号定义位于示例包（assets/资源库/项目存档/示例项目模板/管理配置/信号），
    # 默认作用域仅扫描共享根会导致仓库为空，需显式切换作用域做回归验证。
    set_active_package_id("示例项目模板")
    set_default_definition_schema_view_active_package_id("示例项目模板")
    invalidate_default_signal_repository_cache()
    try:
        repo = get_default_signal_repository()
        payloads = repo.get_all_payloads()
        assert isinstance(payloads, dict) and payloads, "工程应至少存在一个信号定义供回归测试使用"

        # 取一个稳定样本
        sample_signal_id = sorted(payloads.keys())[0]
        sample_payload = payloads[sample_signal_id] or {}
        sample_signal_name = str(sample_payload.get("signal_name") or "").strip() or sample_signal_id

        model = GraphModel(graph_id="g1", graph_name="g1")
        node = model.add_node(
            title=SIGNAL_SEND_NODE_TITLE,
            category="执行节点",
            input_names=["流程入", SIGNAL_NAME_PORT_NAME],
            output_names=["流程出"],
        )
        node.input_constants[SIGNAL_NAME_PORT_NAME] = sample_signal_name

        GraphSemanticPass.apply(model)
        bindings = model.metadata.get("signal_bindings") or {}
        assert isinstance(bindings, dict)
        assert bindings.get(node.id, {}).get("signal_id") == sample_signal_id
        # Pass 会回填稳定 ID（隐藏键）
        assert node.input_constants.get(SEMANTIC_SIGNAL_ID_CONSTANT_KEY) == sample_signal_id

        # 幂等：重复运行不应改变结果
        before = model.serialize().get("metadata")
        GraphSemanticPass.apply(model)
        after = model.serialize().get("metadata")
        assert before == after
    finally:
        set_active_package_id(None)
        set_default_definition_schema_view_active_package_id(None)
        invalidate_default_signal_repository_cache()


def test_graph_semantic_pass_can_build_struct_bindings_from_hint_and_ports() -> None:
    from engine.resources.definition_schema_view import get_default_definition_schema_view

    schema_view = get_default_definition_schema_view()
    all_structs = schema_view.get_all_struct_definitions() or {}
    assert isinstance(all_structs, dict) and all_structs, "工程应至少存在一个结构体定义供回归测试使用"

    chosen_struct_id = ""
    chosen_struct_payload: dict = {}
    chosen_field_name = ""

    # 选择一个“可被 GraphSemanticPass 识别为基础结构体”的样本：
    # - type == "Struct"（或为空）
    # - struct_ype 为空或 basic
    # - fields 里至少有一个 field_name
    for struct_id, payload in all_structs.items():
        if not isinstance(struct_id, str) or not isinstance(payload, dict):
            continue

        type_value = payload.get("type")
        if isinstance(type_value, str) and type_value.strip() and type_value.strip() != "Struct":
            continue

        struct_type_value = payload.get("struct_ype")
        if isinstance(struct_type_value, str) and struct_type_value.strip() and struct_type_value.strip() != "basic":
            continue

        fields_entries = payload.get("fields") or []
        if not isinstance(fields_entries, list) or not fields_entries:
            continue

        for entry in fields_entries:
            if not isinstance(entry, dict):
                continue
            field_name = str(entry.get("field_name") or "").strip()
            if not field_name:
                continue
            chosen_struct_id = struct_id
            chosen_struct_payload = payload
            chosen_field_name = field_name
            break

        if chosen_struct_id:
            break

    assert chosen_struct_id and chosen_field_name

    struct_display_name = (
        str(chosen_struct_payload.get("name") or "").strip()
        or str(chosen_struct_payload.get("struct_name") or "").strip()
        or chosen_struct_id
    )

    model = GraphModel(graph_id="g2", graph_name="g2")
    node = model.add_node(
        title=STRUCT_BUILD_NODE_TITLE,
        category="运算节点",
        input_names=[STRUCT_NAME_PORT_NAME, chosen_field_name],
        output_names=["结果"],
    )
    node.input_constants[STRUCT_NAME_PORT_NAME] = struct_display_name
    node.input_constants[SEMANTIC_STRUCT_ID_CONSTANT_KEY] = chosen_struct_id

    GraphSemanticPass.apply(model)
    bindings = model.metadata.get("struct_bindings") or {}
    assert isinstance(bindings, dict)
    payload = bindings.get(node.id) or {}
    assert payload.get("struct_id") == chosen_struct_id
    assert payload.get("struct_name") == struct_display_name
    assert chosen_field_name in list(payload.get("field_names") or [])

    # 幂等
    before = model.serialize().get("metadata")
    GraphSemanticPass.apply(model)
    after = model.serialize().get("metadata")
    assert before == after


def test_semantic_metadata_keys_have_single_writer() -> None:
    """回归：禁止 Parser/IR/UI 多源写入 signal_bindings/struct_bindings。

    本测试用 AST 扫描 engine/ 与 app/ 的源码，禁止出现以下写入方式：
    - `metadata["signal_bindings"] = ...` / `metadata["struct_bindings"] = ...`
    - 直接调用 GraphModel 的写入 API：`.set_node_signal_binding(...)` / `.set_node_struct_binding(...)`
    - 直接调用 SignalBindingService 写入 API：`.set_node_signal_id(...)`

    允许的写入点应集中在 `engine/graph/semantic/` 的 GraphSemanticPass 内部实现。
    """

    project_root = get_repo_root()
    scan_roots = [project_root / "engine", project_root / "app"]
    forbidden_subscript_keys = {"signal_bindings", "struct_bindings"}
    forbidden_method_names = {"set_node_signal_binding", "set_node_struct_binding", "set_node_signal_id"}

    offenders: list[str] = []

    for base in scan_roots:
        for py_file in base.rglob("*.py"):
            # 允许语义 Pass 内部进行写回（通过变量 key，而非字面量赋值）
            if py_file.as_posix().endswith("engine/graph/semantic/graph_semantic_pass.py"):
                continue

            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))

            for node in ast.walk(tree):
                # 1) 禁止对 bindings key 做字面量赋值：metadata["signal_bindings"] = ...
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if not isinstance(target, ast.Subscript):
                            continue
                        slice_node = target.slice
                        if isinstance(slice_node, ast.Constant) and slice_node.value in forbidden_subscript_keys:
                            offenders.append(str(py_file.relative_to(project_root)))
                            break

                # 2) 禁止直接调用写入 API（未来新增功能若误用会直接回归失败）
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in forbidden_method_names:
                        offenders.append(str(py_file.relative_to(project_root)))

    offenders_unique = sorted(set(offenders))
    assert offenders_unique == [], f"发现疑似多源写入语义元数据的代码：{offenders_unique}"


