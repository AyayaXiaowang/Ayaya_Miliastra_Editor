  function normalizeWinPath(p) {
    return String(p || "").replace(/\\/g, "/");
  }

  function toRelPath(absPath, workspaceRoot) {
    var abs = normalizeWinPath(absPath);
    var root = normalizeWinPath(workspaceRoot);
    if (!abs || !root) return absPath;
    var a = abs.toLowerCase();
    var r = root.toLowerCase();
    if (a.indexOf(r) === 0) {
      var rest = abs.slice(root.length);
      rest = rest.replace(/^\/+/, "");
      return rest || absPath;
    }
    return absPath;
  }

  function pyStr(s) {
    // Use JSON string escaping; safe for python single-line strings
    return JSON.stringify(String(s || ""));
  }

  function pyObj(v) {
    // Backward-compat wrapper: use python literal serializer
    return pyLiteral(v);
  }

  function pyLiteral(v) {
    if (v === null || v === undefined) return "None";
    var t = typeof v;
    if (t === "boolean") return v ? "True" : "False";
    if (t === "number") {
      if (!isFinite(v)) return "None";
      // keep integers without trailing .0
      if (Math.floor(v) === v) return String(v);
      return String(v);
    }
    if (t === "string") return JSON.stringify(String(v));
    if (Array.isArray(v)) {
      var parts = [];
      for (var i = 0; i < v.length; i++) parts.push(pyLiteral(v[i]));
      return "[" + parts.join(", ") + "]";
    }
    if (t === "object") {
      var keys = [];
      for (var k in v) {
        if (Object.prototype.hasOwnProperty.call(v, k)) keys.push(k);
      }
      keys.sort();
      var items = [];
      for (var j = 0; j < keys.length; j++) {
        var kk = keys[j];
        items.push(pyLiteral(String(kk)) + ": " + pyLiteral(v[kk]));
      }
      return "{" + items.join(", ") + "}";
    }
    return pyStr(String(v));
  }

  async function generatePytestFromRecording() {
    var outBox = $("assertionsOutBox");
    if (outBox) outBox.value = "正在生成 pytest...\n";

    var st = await getJson(endpoint("status", "/api/local_sim/status"));
    var wsRoot = (st && st.graph) ? String(st.graph.workspace_root || "") : "";
    var mainGraph = (st && st.graph) ? String(st.graph.graph_code_file || "") : "";
    var uiHtml = (st && st.ui) ? String(st.ui.ui_html_file || "") : "";
    var curLayout = (st && st.ui && typeof st.ui.current_layout_index === "number") ? st.ui.current_layout_index : 0;
    var players = (st && st.players) ? st.players : [];

    var graphs = (st && st.graphs) ? st.graphs : [];
    var ownerName = "自身实体";
    for (var gi = 0; gi < graphs.length; gi++) {
      var g = graphs[gi] || {};
      if (String(g.graph_code_file || "") === mainGraph) {
        ownerName = String(g.owner_entity_name || ownerName);
        break;
      }
    }
    var presentPlayers = (players && players.length) ? players.length : 1;

    var extraMounts = [];
    for (var gi2 = 0; gi2 < graphs.length; gi2++) {
      var g2 = graphs[gi2] || {};
      var f = String(g2.graph_code_file || "");
      if (!f || f === mainGraph) continue;
      extraMounts.push({ graph_code_file: f, owner_entity_name: String(g2.owner_entity_name || ownerName) });
    }

    var actions = recordedActions || [];
    var replayActions = [];
    for (var ai = 0; ai < actions.length; ai++) {
      var act = actions[ai] || {};
      var k = String(act.kind || "");
      if (k !== "ui_click" && k !== "emit_signal" && k !== "step") continue;
      replayActions.push(act);
    }

    var spec = getAssertionsSpecFromBox();
    if (spec.__error) {
      if (outBox) outBox.value = "断言 JSON 解析失败，无法生成 pytest: " + String(spec.__error) + "\n";
      return;
    }
    var assertions = spec.assertions || [];

    var mainGraphRel = toRelPath(mainGraph, wsRoot);
    var uiHtmlRel = toRelPath(uiHtml, wsRoot);
    var extraMountsRel = [];
    for (var em = 0; em < extraMounts.length; em++) {
      extraMountsRel.push({
        graph_code_file: toRelPath(extraMounts[em].graph_code_file, wsRoot),
        owner_entity_name: String(extraMounts[em].owner_entity_name || "")
      });
    }

    var code = [];
    code.push("from __future__ import annotations");
    code.push("");
    code.push("from pathlib import Path");
    code.push("");
    code.push("import pytest");
    code.push("");
    code.push("import app.runtime.engine.game_state as game_state_module");
    code.push("from app.runtime.services.local_graph_sim_server import _build_layout_html_map, _extract_merged_lv_defaults");
    code.push("from app.runtime.services.local_graph_simulator import GraphMountSpec, build_local_graph_sim_session");
    code.push("from engine.validate.node_graph_validator import validate_file as validate_node_graph_file");
    code.push("from tests._helpers.project_paths import get_repo_root");
    code.push("");
    code.push("");
    code.push("def _p(repo_root: Path, rel_or_abs: str) -> Path:");
    code.push("    p = Path(str(rel_or_abs))");
    code.push("    if p.is_absolute():");
    code.push("        return p.resolve()");
    code.push("    return (repo_root / str(rel_or_abs)).resolve()");
    code.push("");
    code.push("");
    code.push("@pytest.fixture");
    code.push("def _clock(monkeypatch):");
    code.push('    state = {"t": 0.0}');
    code.push("    monkeypatch.setattr(game_state_module.time, \"monotonic\", lambda: float(state[\"t\"]))");
    code.push("    monkeypatch.setattr(game_state_module, \"print\", lambda *args, **kwargs: None, raising=False)");
    code.push("");
    code.push("    def advance(dt: float) -> float:");
    code.push("        state[\"t\"] = float(state[\"t\"]) + float(dt)");
    code.push("        return float(state[\"t\"])");
    code.push("");
    code.push("    return state, advance");
    code.push("");
    code.push("");
    code.push("def _get_lv_root(session) -> dict:");
    code.push("    game = session.game");
    code.push("    eid = str(getattr(game, \"ui_binding_root_entity_id\", \"\") or \"\").strip()");
    code.push("    cv = getattr(game, \"custom_variables\", {}) or {}");
    code.push("    if eid and isinstance(cv.get(eid), dict):");
    code.push("        return cv.get(eid) or {}");
    code.push("    # fallback: first entity that has UI* vars");
    code.push("    for _eid, m in (cv or {}).items():");
    code.push("        if not isinstance(m, dict):");
    code.push("            continue");
    code.push("        for k in m.keys():");
    code.push("            if str(k).startswith(\"UI\"):");
    code.push("                return m");
    code.push("    return {}");
    code.push("");
    code.push("");
    code.push("def _get_path(root, parts: list[str]):");
    code.push("    cur = root");
    code.push("    for p in parts:");
    code.push("        if cur is None:");
    code.push("            return None");
    code.push("        key = str(p or \"\").strip()");
    code.push("        if key == \"\":");
    code.push("            return None");
    code.push("        if isinstance(cur, list):");
    code.push("            try:");
    code.push("                idx = int(key)");
    code.push("            except Exception:");
    code.push("                return None");
    code.push("            if idx < 0 or idx >= len(cur):");
    code.push("                return None");
    code.push("            cur = cur[idx]");
    code.push("            continue");
    code.push("        if isinstance(cur, dict):");
    code.push("            cur = cur.get(key)");
    code.push("            continue");
    code.push("        return None");
    code.push("    return cur");
    code.push("");
    code.push("");
    code.push("def _resolve_path(session, path: str):");
    code.push("    text = str(path or \"\").strip()");
    code.push("    if text.startswith(\"lv.\"):");
    code.push("        parts = text[3:].split(\".\")");
    code.push("        return _get_path(_get_lv_root(session), parts)");
    code.push("    if text.startswith(\"graph_variables.\"):");
    code.push("        parts = text[len(\"graph_variables.\"):].split(\".\")");
    code.push("        return _get_path(getattr(session.game, \"graph_variables\", {}) or {}, parts)");
    code.push("    if text.startswith(\"local_variables.\"):");
    code.push("        parts = text[len(\"local_variables.\"):].split(\".\")");
    code.push("        return _get_path(getattr(session.game, \"local_variables\", {}) or {}, parts)");
    code.push("    if text.startswith(\"custom_variables.\"):");
    code.push("        rest = text[len(\"custom_variables.\"):]");
    code.push("        parts = rest.split(\".\")");
    code.push("        eid = str(parts[0] or \"\").strip()");
    code.push("        return _get_path((getattr(session.game, \"custom_variables\", {}) or {}).get(eid, {}), parts[1:])");
    code.push("    if text.startswith(\"cv.\"):");
    code.push("        rest = text[len(\"cv.\"):]");
    code.push("        parts = rest.split(\".\")");
    code.push("        eid = str(parts[0] or \"\").strip()");
    code.push("        return _get_path((getattr(session.game, \"custom_variables\", {}) or {}).get(eid, {}), parts[1:])");
    code.push("    raise AssertionError(f\"unknown path prefix: {text}\")");
    code.push("");
    code.push("");
    code.push("def _assert_patch_contains(patches: list[dict], *, op: str, ui_key_contains: str = \"\", visible=None, state_contains: str = \"\", layout_index=None, group_index=None) -> None:");
    code.push("    for p in list(patches or []):");
    code.push("        if str(p.get(\"op\") or \"\") != str(op):");
    code.push("            continue");
    code.push("        if ui_key_contains:");
    code.push("            if ui_key_contains not in str(p.get(\"ui_key\") or \"\"):");
    code.push("                continue");
    code.push("        if visible is not None:");
    code.push("            if bool(p.get(\"visible\")) != bool(visible):");
    code.push("                continue");
    code.push("        if state_contains:");
    code.push("            if state_contains not in str(p.get(\"state\") or \"\"):"); 
    code.push("                continue");
    code.push("        if layout_index is not None:");
    code.push("            if int(p.get(\"layout_index\") or 0) != int(layout_index):");
    code.push("                continue");
    code.push("        if group_index is not None:");
    code.push("            if int(p.get(\"group_index\") or 0) != int(group_index):");
    code.push("                continue");
    code.push("        return");
    code.push("    raise AssertionError(f\"patch not found: op={op} ui_key_contains={ui_key_contains!r} visible={visible}\")");
    code.push("");
    code.push("");
    code.push("def _assert_trace_contains(events: list, *, kind: str = \"\", message_contains: str = \"\", details_contains: str = \"\") -> None:");
    code.push("    for ev in list(events or []):");
    code.push("        e = ev.to_dict() if hasattr(ev, \"to_dict\") else dict(ev)");
    code.push("        if kind and str(e.get(\"kind\") or \"\") != str(kind):");
    code.push("            continue");
    code.push("        if message_contains and message_contains not in str(e.get(\"message\") or \"\"):");
    code.push("            continue");
    code.push("        if details_contains:");
    code.push("            import json");
    code.push("            text = json.dumps(e.get(\"details\") or {}, ensure_ascii=False)");
    code.push("            if details_contains not in text:");
    code.push("                continue");
    code.push("        return");
    code.push("    raise AssertionError(f\"trace not found: kind={kind!r} message~={message_contains!r} details~={details_contains!r}\")");
    code.push("");
    code.push("");
    code.push("def test_local_sim_generated_scenario(_clock):");
    code.push("    _state, advance = _clock");
    code.push("    repo_root = get_repo_root()");
    code.push("");
    code.push("    graphs = [");
    code.push("        _p(repo_root, " + pyStr(mainGraphRel) + "),");
    for (var em2 = 0; em2 < extraMountsRel.length; em2++) {
      code.push("        _p(repo_root, " + pyStr(extraMountsRel[em2].graph_code_file) + "),");
    }
    code.push("    ]");
    code.push("    for path in graphs:");
    code.push("        passed, errors, warnings = validate_node_graph_file(path)");
    code.push("        assert passed, f\"graph validate failed: {path} errors={len(errors)} warnings={len(warnings)} {errors[:5]}\"");
    code.push("");
    code.push("    extra = [");
    for (var em3 = 0; em3 < extraMountsRel.length; em3++) {
      code.push("        GraphMountSpec(graph_code_file=_p(repo_root, " + pyStr(extraMountsRel[em3].graph_code_file) + "), owner_entity_name=" + pyStr(extraMountsRel[em3].owner_entity_name) + "),");
    }
    code.push("    ]");
    code.push("");
    code.push("    session = build_local_graph_sim_session(");
    code.push("        workspace_root=repo_root,");
    code.push("        graph_code_file=_p(repo_root, " + pyStr(mainGraphRel) + "),");
    code.push("        owner_entity_name=" + pyStr(ownerName) + ",");
    code.push("        present_player_count=" + String(presentPlayers) + ",");
    code.push("        extra_graph_mounts=extra,");
    code.push("    )");
    code.push("");
    code.push("    # align current layout for layout-gated graphs");
    code.push("    for p in session.game.get_present_player_entities():");
    code.push("        session.game.ui_current_layout_by_player[str(p.entity_id)] = int(" + String(curLayout) + ")");
    code.push("");
    code.push("    # inject lv.* defaults from UI HTML (best-effort)");
    code.push("    ui_html = _p(repo_root, " + pyStr(uiHtmlRel) + ")");
    code.push("    if ui_html.is_file():");
    code.push("        layout_map = _build_layout_html_map(ui_html)");
    code.push("        merged = _extract_merged_lv_defaults(entry_ui_file=ui_html, layout_html_by_index=layout_map)");
    code.push("        if merged:");
    code.push("            session.game.set_ui_lv_defaults(merged)");
    code.push("");
    code.push("    actions = " + pyLiteral(replayActions));
    code.push("    assertions = " + pyLiteral(assertions));
    code.push("");
    code.push("    last_patches = []");
    code.push("    last_trace_slice = []");
    code.push("");
    code.push("    for i, act in enumerate(actions):");
    code.push("        kind = str(act.get(\"kind\") or \"\")");
    code.push("        details = act.get(\"details\") or {}");
    code.push("        base = len(session.game.trace_recorder.events)");
    code.push("");
    code.push("        patches = []");
    code.push("        if kind == \"ui_click\":");
    code.push("            patches = session.trigger_ui_click(");
    code.push("                data_ui_key=str(details.get(\"data_ui_key\") or \"\"),");
    code.push("                data_ui_state_group=str(details.get(\"data_ui_state_group\") or \"\"),");
    code.push("                data_ui_state=str(details.get(\"data_ui_state\") or \"\"),");
    code.push("            )");
    code.push("        elif kind == \"emit_signal\":");
    code.push("            sid = str(details.get(\"resolved_signal_id\") or details.get(\"signal_id\") or \"\")");
    code.push("            params = details.get(\"params\") or {}");
    code.push("            patches = session.emit_signal(signal_id=sid, params=dict(params))");
    code.push("        elif kind == \"step\":");
    code.push("            dt = float((details.get(\"dt\") or 0.1))");
    code.push("            advance(dt)");
    code.push("            session.game.tick(now=float(_state[\"t\"]), max_fires=1)");
    code.push("            patches = session.drain_ui_patches()");
    code.push("        else:");
    code.push("            continue");
    code.push("");
    code.push("        last_patches = list(patches or [])");
    code.push("        last_trace_slice = list(session.game.trace_recorder.events[base:])");
    code.push("");
    code.push("        # per-action assertions");
    code.push("        for a in list(assertions or []):");
    code.push("            after_i = a.get(\"after_action\", None)");
    code.push("            if after_i is None:");
    code.push("                continue");
    code.push("            if int(after_i) != int(i):");
    code.push("                continue");
    code.push("            typ = str(a.get(\"type\") or \"\")");
    code.push("            if typ == \"patch_contains\":");
    code.push("                _assert_patch_contains(last_patches, op=str(a.get(\"op\") or \"\"), ui_key_contains=str(a.get(\"ui_key_contains\") or \"\"), visible=a.get(\"visible\", None), state_contains=str(a.get(\"state_contains\") or \"\"), layout_index=a.get(\"layout_index\", None), group_index=a.get(\"group_index\", None))");
    code.push("            elif typ == \"path_equals\":");
    code.push("                got = _resolve_path(session, str(a.get(\"path\") or \"\"))");
    code.push("                assert got == a.get(\"equals\"), f\"path_equals failed: {a.get('path')} got={got!r} expected={a.get('equals')!r}\"");
    code.push("            elif typ == \"trace_contains\":");
    code.push("                _assert_trace_contains(last_trace_slice, kind=str(a.get(\"kind\") or \"\"), message_contains=str(a.get(\"message_contains\") or \"\"), details_contains=str(a.get(\"details_contains\") or \"\"))");
    code.push("");
    code.push("    # end-of-scenario assertions (after_action missing or -1)");
    code.push("    for a in list(assertions or []):");
    code.push("        after_i = a.get(\"after_action\", -1)");
    code.push("        if after_i is not None and int(after_i) != -1:");
    code.push("            continue");
    code.push("        typ = str(a.get(\"type\") or \"\")");
    code.push("        if typ == \"patch_contains\":");
    code.push("            _assert_patch_contains(last_patches, op=str(a.get(\"op\") or \"\"), ui_key_contains=str(a.get(\"ui_key_contains\") or \"\"), visible=a.get(\"visible\", None), state_contains=str(a.get(\"state_contains\") or \"\"), layout_index=a.get(\"layout_index\", None), group_index=a.get(\"group_index\", None))");
    code.push("        elif typ == \"path_equals\":");
    code.push("            got = _resolve_path(session, str(a.get(\"path\") or \"\"))");
    code.push("            assert got == a.get(\"equals\"), f\"path_equals failed: {a.get('path')} got={got!r} expected={a.get('equals')!r}\"");
    code.push("        elif typ == \"trace_contains\":");
    code.push("            _assert_trace_contains(last_trace_slice, kind=str(a.get(\"kind\") or \"\"), message_contains=str(a.get(\"message_contains\") or \"\"), details_contains=str(a.get(\"details_contains\") or \"\"))");
    code.push("");

    outBox.value = code.join("\n") + "\n";
    outBox.scrollTop = 0;
  }

