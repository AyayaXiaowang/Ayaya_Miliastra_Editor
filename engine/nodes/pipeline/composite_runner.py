from __future__ import annotations

from pathlib import Path
from typing import Dict

from engine.nodes.node_definition_loader import NodeDef
from .composite_discovery import discover_composite_files
from .composite_parse import parse_composite_defs
from .composite_validate import validate_composites
from .composite_expand import expand_composites
from .composite_augment import augment_composites


def run_composite_pipeline(
    workspace_path: Path,
    base_node_library: Dict[str, NodeDef],
    verbose: bool = False,
) -> Dict[str, NodeDef]:
    """
    运行复合节点子管线：
      discovery → parse → validate → expand → augment
    返回复合节点的 NodeDef 字典。
    """
    files = discover_composite_files(workspace_path)
    parsed = parse_composite_defs(files=files, base_node_library=base_node_library, workspace_path=workspace_path, verbose=verbose)
    validated = validate_composites(parsed)
    expanded = expand_composites(validated)
    augmented = augment_composites(expanded, base_node_library=base_node_library)
    return augmented

