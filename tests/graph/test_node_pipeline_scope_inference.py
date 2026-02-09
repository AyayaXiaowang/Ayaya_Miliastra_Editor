from __future__ import annotations

from pathlib import Path

from engine.nodes.pipeline.normalizer import normalize_specs
from engine.nodes.pipeline.types import ExtractedSpec


def test_infer_scopes_from_file_path_when_scopes_missing() -> None:
    extracted = [
        ExtractedSpec(
            file_path=Path("plugins/nodes/server/查询节点/获取自定义变量.py"),
            name="获取自定义变量",
            category="查询节点",
            inputs=[("目标实体", "实体"), ("变量名", "字符串")],
            outputs=[("变量值", "泛型")],
            doc_reference="服务器节点/查询节点/查询节点.md",
            scopes=[],
        ),
        ExtractedSpec(
            file_path=Path("plugins/nodes/client/查询节点/获取自定义变量.py"),
            name="获取自定义变量",
            category="查询节点",
            inputs=[("目标实体", "实体"), ("变量名", "字符串")],
            outputs=[("变量值", "泛型")],
            doc_reference="客户端节点/查询节点/查询节点.md",
            scopes=[],
        ),
    ]
    normalized = normalize_specs(extracted)
    assert len(normalized) == 2
    assert normalized[0].scopes == ["server"]
    assert normalized[1].scopes == ["client"]


def test_infer_scopes_from_doc_reference_when_path_not_scoped() -> None:
    extracted = [
        ExtractedSpec(
            file_path=Path("plugins/nodes/common/查询节点/示例节点.py"),
            name="示例节点",
            category="查询节点",
            inputs=[("输入A", "整数")],
            outputs=[("输出A", "整数")],
            doc_reference="客户端节点/查询节点/查询节点.md",
            scopes=[],
        )
    ]
    normalized = normalize_specs(extracted)
    assert len(normalized) == 1
    # doc_reference 不再参与 scopes 推断：未显式声明 scopes 且路径不带 server/client 时，保持为空
    assert normalized[0].scopes == []


