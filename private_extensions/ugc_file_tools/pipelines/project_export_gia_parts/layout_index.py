from __future__ import annotations

from .ui_export_context import UiExportContext
from .ui_infer import _infer_layout_index_html_stem_from_graph_variable_description


class LayoutIndexAutoFiller:
    """
    布局索引（GraphVariables）自动回填器。

    真源口径（已验证）：
    - 节点 `Switch Current Interface Layout(382)` 的“布局索引”(Int) 实际传入的是 **layout root GUID（107374xxxx）**，
      而不是 1..N 的序号。
    """

    def __init__(self, *, ui_ctx: UiExportContext) -> None:
        self._ui_ctx = ui_ctx
        self._layout_root_guid_cache: dict[str, int] = {}
        self._layout_root_guid_missing: set[str] = set()

    def try_resolve_layout_root_guid_by_layout_name(self, layout_name: str) -> int | None:
        stem = str(layout_name or "").strip()
        if stem == "":
            return None
        if stem in self._layout_root_guid_cache:
            return int(self._layout_root_guid_cache[stem])
        if stem in self._layout_root_guid_missing:
            return None

        ui_index = self._ui_ctx.selected_ui_export_record_ui_index
        ui_key_to_guid_registry = self._ui_ctx.ui_key_to_guid_registry
        layout_name_to_export_pos = self._ui_ctx.layout_name_to_export_pos

        # 1) 首选：从 output_gil 的 UI records 里按“布局 root name”反查 GUID（最可靠）
        if ui_index is not None:
            try_guids = ui_index.guids_by_name.get(stem) or []
            roots = [int(g) for g in try_guids if ui_index.parent_by_guid.get(int(g)) is None]
            if len(roots) == 1:
                self._layout_root_guid_cache[stem] = int(roots[0])
                return int(roots[0])

        # 2) 直接命中：registry 已包含 `LAYOUT_INDEX__HTML__<layout_name>`（layout root GUID 口径）
        if ui_key_to_guid_registry is not None:
            direct = ui_key_to_guid_registry.get(f"LAYOUT_INDEX__HTML__{stem}")
            if isinstance(direct, int) and int(direct) > 1_000_000_000:
                self._layout_root_guid_cache[stem] = int(direct)
                return int(direct)

        # 3) 通过 UI 导出记录的导出顺序（layout_names[i] -> ui_bundle_i）从 registry 做桥接
        pos = layout_name_to_export_pos.get(stem)
        if isinstance(pos, int) and ui_key_to_guid_registry is not None:
            suffix = f"__ui_bundle_{int(pos)}"

            # 新口径（推荐）：LAYOUT_INDEX__layout_html_import_*__ui_bundle_i -> layout_root_guid
            candidates: list[int] = []
            for k, v in ui_key_to_guid_registry.items():
                kk = str(k)
                if not kk.startswith("LAYOUT_INDEX__layout_html_import_"):
                    continue
                if not kk.endswith(suffix):
                    continue
                if isinstance(v, int) and int(v) > 1_000_000_000:
                    candidates.append(int(v))
            if candidates:
                resolved = int(max(candidates))
                self._layout_root_guid_cache[stem] = int(resolved)
                return int(resolved)

            # 旧口径兼容：LAYOUT__layout_html_import_*__ui_bundle_i -> layout_root_guid
            candidates2: list[int] = []
            for k, v in ui_key_to_guid_registry.items():
                kk = str(k)
                if not kk.startswith("LAYOUT__layout_html_import_"):
                    continue
                if not kk.endswith(suffix):
                    continue
                if isinstance(v, int) and int(v) > 1_000_000_000:
                    candidates2.append(int(v))
            if candidates2:
                resolved = int(max(candidates2))
                self._layout_root_guid_cache[stem] = int(resolved)
                return int(resolved)

            # fallback：部分链路只有 HTML bundle stem 别名（ui_bundle_i）
            v2 = ui_key_to_guid_registry.get(f"LAYOUT_INDEX__HTML__ui_bundle_{int(pos)}")
            if isinstance(v2, int) and int(v2) > 1_000_000_000:
                self._layout_root_guid_cache[stem] = int(v2)
                return int(v2)

        self._layout_root_guid_missing.add(stem)
        return None

    def autofill_graph_variables_layout_index(self, *, graph_json_object: dict[str, object]) -> list[dict[str, object]]:
        """
        回填 graph_variables 中的 “布局索引_*” 默认值（0 -> layout root GUID）。
        会原地修改 graph_json_object。
        """
        ui_key_to_guid_registry = self._ui_ctx.ui_key_to_guid_registry
        graph_variables_layout_index_auto_filled: list[dict[str, object]] = []
        graph_model_payload_for_layout = graph_json_object.get("data")
        if isinstance(graph_model_payload_for_layout, dict):
            raw_graph_vars = graph_model_payload_for_layout.get("graph_variables")
            if isinstance(raw_graph_vars, list):
                for var in raw_graph_vars:
                    if not isinstance(var, dict):
                        continue
                    var_name = str(var.get("name") or "").strip()
                    if not var_name.startswith("布局索引_"):
                        continue
                    var_type_text = str(var.get("variable_type") or "").strip()
                    if var_type_text != "整数":
                        continue

                    old_default = var.get("default_value")
                    if isinstance(old_default, int) and int(old_default) != 0:
                        continue
                    if isinstance(old_default, str) and old_default.strip() not in {"", "0"}:
                        continue

                    stem = _infer_layout_index_html_stem_from_graph_variable_description(str(var.get("description") or ""))
                    if stem is None:
                        continue
                    resolved_layout_root_guid = self.try_resolve_layout_root_guid_by_layout_name(str(stem))
                    if resolved_layout_root_guid is None or int(resolved_layout_root_guid) <= 1_000_000_000:
                        continue

                    var["default_value"] = int(resolved_layout_root_guid)
                    graph_variables_layout_index_auto_filled.append(
                        {
                            "variable": str(var_name),
                            "html_stem": str(stem),
                            "layout_guid": int(resolved_layout_root_guid),
                        }
                    )

                    if ui_key_to_guid_registry is not None:
                        ui_key_to_guid_registry[f"LAYOUT_INDEX__HTML__{stem}"] = int(resolved_layout_root_guid)

        return graph_variables_layout_index_auto_filled

