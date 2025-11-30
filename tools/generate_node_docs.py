from __future__ import annotations

from pathlib import Path
from typing import Dict

from engine.nodes import NodeDef
from engine.nodes import get_node_registry
from engine.utils import sanitize_node_filename


WORKSPACE = Path(__file__).resolve().parents[1]
DOC_ROOT = WORKSPACE / "assets" / "资源库" / "节点图" / "节点文档"


def _render_node_markdown(node: NodeDef) -> str:
    lines = []
    lines.append(f"# {node.category} / {node.name}\n\n")
    if node.description:
        lines.append(f"> {node.description}\n\n")
    lines.append("## 作用域\n")
    lines.append("- " + ", ".join(node.scopes) + "\n\n")
    lines.append("## 端口\n")
    lines.append("### 输入\n")
    for name in node.inputs:
        lines.append(f"- {name}: {node.input_types.get(name, '未知')}\n")
    lines.append("\n### 输出\n")
    for name in node.outputs:
        lines.append(f"- {name}: {node.output_types.get(name, '未知')}\n")
    lines.append("\n")
    if node.doc_reference:
        lines.append(f"参考文档: {node.doc_reference}\n")
    return "".join(lines)


def main() -> None:
    registry = get_node_registry(WORKSPACE, include_composite=True)
    lib: Dict[str, NodeDef] = registry.get_library()
    # 分组写入
    DOC_ROOT.mkdir(parents=True, exist_ok=True)
    for key, node in lib.items():
        # 跳过复合节点（其文档由复合节点管理器维护）
        if getattr(node, "is_composite", False):
            continue
        out_dir = DOC_ROOT / node.category
        out_dir.mkdir(parents=True, exist_ok=True)
        file_stem = sanitize_node_filename(node.name)
        out_file = out_dir / f"{file_stem}.md"
        out_file.write_text(_render_node_markdown(node), encoding="utf-8")
    print(f"OK: 生成 {len(lib)} 条节点文档骨架（含别名条目指向同一文件）")


if __name__ == "__main__":
    main()


