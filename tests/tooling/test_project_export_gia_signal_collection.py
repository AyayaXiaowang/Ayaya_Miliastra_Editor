from __future__ import annotations

import json
import sys
from pathlib import Path


def _ensure_private_extensions_importable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    private_extensions_root = (repo_root / "private_extensions").resolve()
    if str(private_extensions_root) not in sys.path:
        sys.path.insert(0, str(private_extensions_root))


def test_project_export_gia_collects_listen_signal_specs() -> None:
    """
    回归：导出节点图 `.gia` 的“自包含信号”收集必须包含 `监听信号`。

    现象（历史 bug）：
    - 图里同时存在多个信号，其中某些信号仅以 `监听信号` 形式出现；
    - 若导出阶段只扫描 `发送信号`，会漏打包该信号的 node_def GraphUnits；
    - 导入 `.gia` 后监听信号节点无法展开参数端口，导致大量连线断开。
    """
    _ensure_private_extensions_importable()

    repo_root = Path(__file__).resolve().parents[2]
    graph_code_file = (
        repo_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_踏板开关_信号广播.py"
    )

    from ugc_file_tools.commands.export_graph_model_json_from_graph_code import export_graph_model_json_from_graph_code
    from ugc_file_tools.pipelines.project_export_gia import _collect_used_signal_specs_from_graph_payload

    report = export_graph_model_json_from_graph_code(
        graph_code_file=Path(graph_code_file),
        output_json_file=Path("_pytest_signal_collection.graph_model.json"),
        graph_generater_root=Path(repo_root),
    )
    exported_graph_model_json_path = Path(str(report["output_json"])).resolve()
    exported = json.loads(exported_graph_model_json_path.read_text(encoding="utf-8"))

    graph_payload = exported.get("data")
    assert isinstance(graph_payload, dict)

    specs = _collect_used_signal_specs_from_graph_payload(
        graph_payload=graph_payload,
        signal_params_by_name={},
        composite_mgr=None,
        composite_loaded={},
    )

    names = {str(x.get("signal_name") or "") for x in specs if isinstance(x, dict)}
    assert names == {"通用踏板开关_状态变化", "通用踏板开关_激活确认"}
    assert len(specs) == 2

