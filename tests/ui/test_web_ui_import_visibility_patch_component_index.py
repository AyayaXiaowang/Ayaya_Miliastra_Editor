from __future__ import annotations

from pathlib import Path

import pytest


def _build_record_with_two_node14_components() -> dict:
    # 最小化 record：只需要 component_list + 503/14 节点即可。
    # 其中：
    # - component_list[0] 也包含 node14（可能是其它语义的 node14，旧实现会误写这里）
    # - component_list[1] 才是“初始隐藏”的真源位置（必须优先写这里）
    return {
        "505": [
            {"503": {"14": {"501": 5}}},  # component 0
            {"503": {"14": {"501": 5}}},  # component 1 (authoritative)
            {"503": {}},  # component 2 (placeholder)
        ]
    }


def test_apply_visibility_patch_targets_component_1(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    private_extensions_root = repo_root / "private_extensions"
    monkeypatch.syspath_prepend(str(private_extensions_root))

    from ugc_file_tools.ui_patchers.web_ui_import_visibility import apply_visibility_patch

    record = _build_record_with_two_node14_components()

    # 先写隐藏：应该写到 component_list[1]['503']['14']['502']=1
    changed = apply_visibility_patch(record, visible=False)
    assert changed == 1

    node14_0 = record["505"][0]["503"]["14"]
    node14_1 = record["505"][1]["503"]["14"]
    assert node14_0.get("502") is None, "component[0] 不应承载初始隐藏位"
    assert node14_1.get("502") == 1, "component[1] 必须写入初始隐藏位"

    # 再写回可见：应删除 component[1] 的 502
    changed2 = apply_visibility_patch(record, visible=True)
    assert changed2 == 1
    assert node14_1.get("502") is None
    assert node14_0.get("502") is None


def test_try_get_record_visibility_flag_reads_component_1(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    private_extensions_root = repo_root / "private_extensions"
    monkeypatch.syspath_prepend(str(private_extensions_root))

    from ugc_file_tools.ui_patchers.web_ui_import_visibility import apply_visibility_patch, try_get_record_visibility_flag

    record = _build_record_with_two_node14_components()
    assert try_get_record_visibility_flag(record) == 1  # visible

    apply_visibility_patch(record, visible=False)
    assert try_get_record_visibility_flag(record) == 0  # hidden

