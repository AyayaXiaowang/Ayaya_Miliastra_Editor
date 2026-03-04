  function getSnapshotPath(snapshot, pathExpr) {
    var text = trim(pathExpr);
    if (!text) return { ok: false, error: "path 为空" };
    if (!snapshot || typeof snapshot !== "object") return { ok: false, error: "snapshot 为空" };

    function _getPath(root, parts) {
      var cur = root;
      for (var i = 0; i < parts.length; i++) {
        if (cur === null || cur === undefined) return undefined;
        var p = String(parts[i] || "");
        if (!p) return undefined;
        if (Array.isArray(cur)) {
          var idx = parseInt(p, 10);
          if (isNaN(idx) || idx < 0 || idx >= cur.length) return undefined;
          cur = cur[idx];
          continue;
        }
        if (typeof cur === "object") {
          if (Object.prototype.hasOwnProperty.call(cur, p)) cur = cur[p];
          else if (p in cur) cur = cur[p];
          else return undefined;
          continue;
        }
        return undefined;
      }
      return cur;
    }

    // lv.* is derived from binding root entity custom variables
    if (text.indexOf("lv.") === 0) {
      var rest = text.slice(3);
      var parts = rest.split(".");
      var ui = snapshot.ui || {};
      var eid = String(ui.ui_binding_root_entity_id || "");
      var cv = (((snapshot.variables || {}).custom_variables) || {});
      var lvRoot = (eid && cv && typeof cv === "object") ? cv[eid] : null;
      if (!lvRoot || typeof lvRoot !== "object") return { ok: false, error: "lv 根实体未确定（ui_binding_root_entity_id 为空或 custom_variables 缺失）" };
      return { ok: true, value: _getPath(lvRoot, parts) };
    }
    if (text.indexOf("graph_variables.") === 0) {
      var rest2 = text.slice("graph_variables.".length);
      var parts2 = rest2.split(".");
      var gv = ((snapshot.variables || {}).graph_variables) || {};
      return { ok: true, value: _getPath(gv, parts2) };
    }
    if (text.indexOf("local_variables.") === 0) {
      var rest3 = text.slice("local_variables.".length);
      var parts3 = rest3.split(".");
      var lv2 = ((snapshot.variables || {}).local_variables) || {};
      return { ok: true, value: _getPath(lv2, parts3) };
    }
    if (text.indexOf("custom_variables.") === 0 || text.indexOf("cv.") === 0) {
      var prefix = (text.indexOf("cv.") === 0) ? "cv." : "custom_variables.";
      var rest4 = text.slice(prefix.length);
      var parts4 = rest4.split(".");
      var eid2 = String(parts4.shift() || "");
      if (!eid2) return { ok: false, error: "custom_variables 需要 entity_id：custom_variables.<entity_id>.<var>..." };
      var cv2 = ((snapshot.variables || {}).custom_variables) || {};
      var root2 = cv2[eid2];
      return { ok: true, value: _getPath(root2, parts4) };
    }
    if (text.indexOf("ui.") === 0) {
      var rest5 = text.slice(3);
      var parts5 = rest5.split(".");
      return { ok: true, value: _getPath(snapshot.ui || {}, parts5) };
    }
    return { ok: false, error: "未知 path 前缀（支持：lv./graph_variables./local_variables./custom_variables./cv./ui.）" };
  }

  function evalAssertionAgainstLast(action, snapshot, assertion) {
    var a = assertion || {};
    var typ = String(a.type || "");
    if (!typ) return { ok: false, message: "断言缺少 type" };

    if (typ === "patch_contains") {
      var op = String(a.op || "");
      if (!op) return { ok: false, message: "patch_contains 缺少 op" };
      var uiKeyContains = String(a.ui_key_contains || "");
      var hasVisible = (typeof a.visible === "boolean");
      var visible = a.visible;
      var stateContains = String(a.state_contains || "");
      var hasLayout = (typeof a.layout_index === "number");
      var layoutIndex = a.layout_index;
      var hasGroup = (typeof a.group_index === "number");
      var groupIndex = a.group_index;

      var patches = (action && action.patches) ? action.patches : [];
      var matched = false;
      for (var i = 0; i < patches.length; i++) {
        var p = patches[i] || {};
        if (String(p.op || "") !== op) continue;
        if (uiKeyContains) {
          var uk = String(p.ui_key || "");
          if (uk.indexOf(uiKeyContains) < 0) continue;
        }
        if (hasVisible && p.visible !== visible) continue;
        if (stateContains) {
          var st = String(p.state || "");
          if (st.indexOf(stateContains) < 0) continue;
        }
        if (hasLayout && parseInt(p.layout_index, 10) !== parseInt(layoutIndex, 10)) continue;
        if (hasGroup && parseInt(p.group_index, 10) !== parseInt(groupIndex, 10)) continue;
        matched = true;
        break;
      }
      return { ok: matched, message: matched ? "OK" : ("未找到匹配 patch: op=" + op + (uiKeyContains ? (" ui_key~=" + uiKeyContains) : "")) };
    }

    if (typ === "path_equals") {
      var path = String(a.path || "");
      if (!path) return { ok: false, message: "path_equals 缺少 path" };
      var r = getSnapshotPath(snapshot, path);
      if (!r.ok) return { ok: false, message: "path 解析失败: " + String(r.error || "") };
      var got = r.value;
      var expected = a.equals;
      var pass = deepEqual(got, expected);
      return { ok: pass, message: pass ? "OK" : ("不相等: " + path + " got=" + shortJson(got, 220) + " expected=" + shortJson(expected, 220)) };
    }

    if (typ === "trace_contains") {
      var wantKind = String(a.kind || "");
      var msgSub = String(a.message_contains || "");
      var detSub = String(a.details_contains || "");
      if (!wantKind && !msgSub && !detSub) return { ok: false, message: "trace_contains 至少需要 kind/message_contains/details_contains 之一" };
      if (!action) return { ok: false, message: "last_action 为空" };
      var ts = action.timestamp;
      if (typeof ts !== "number") ts = parseFloat(ts);
      if (!ts || isNaN(ts)) return { ok: false, message: "last_action 缺少 timestamp" };
      var start = ts - 0.05;
      var end = ts + 2.0;
      var hit = false;
      for (var i2 = 0; i2 < traceEventsCache.length; i2++) {
        var e = traceEventsCache[i2] || {};
        var et = (typeof e.timestamp === "number") ? e.timestamp : parseFloat(e.timestamp);
        if (!et || isNaN(et) || et < start || et > end) continue;
        if (wantKind && String(e.kind || "") !== wantKind) continue;
        if (msgSub && String(e.message || "").indexOf(msgSub) < 0) continue;
        if (detSub) {
          var d = "";
          try { d = JSON.stringify(e.details || {}); } catch (_e) { d = String(e.details || ""); }
          if (d.indexOf(detSub) < 0) continue;
        }
        hit = true;
        break;
      }
      return { ok: hit, message: hit ? "OK" : "未命中 trace（建议查看右侧 Trace 全量）" };
    }

    return { ok: false, message: "未知断言 type: " + typ };
  }

  function pointerToDotPath(ptr, snapshot) {
    var path = String(ptr || "");
    if (!path || path[0] !== "/") return "";
    // decode JSON pointer escaping
    function unesc(t) { return String(t).replace(/~1/g, "/").replace(/~0/g, "~"); }
    var parts = path.split("/").slice(1).map(unesc);
    if (parts.length < 2) return "";
    if (parts[0] !== "variables") return "";

    if (parts[1] === "graph_variables") {
      return "graph_variables." + parts.slice(2).join(".");
    }
    if (parts[1] === "local_variables") {
      return "local_variables." + parts.slice(2).join(".");
    }
    if (parts[1] === "custom_variables") {
      if (parts.length < 4) return "";
      var eid = String(parts[2] || "");
      var ui = snapshot && snapshot.ui ? snapshot.ui : {};
      var root = String(ui.ui_binding_root_entity_id || "");
      if (root && eid === root) return "lv." + parts.slice(3).join(".");
      return "custom_variables." + eid + "." + parts.slice(3).join(".");
    }
    return "";
  }

  async function fillAssertionsFromLastAction() {
    var outBox = $("assertionsOutBox");
    if (outBox) outBox.value = "正在提取断言...\n";

    var lastPayload = await getJson(endpoint("last_action", "/api/local_sim/last_action"));
    var last = (lastPayload && lastPayload.last_action) ? lastPayload.last_action : null;
    if (!last) {
      if (outBox) outBox.value = "没有 last_action，先点击 UI 或发送信号。\n";
      return;
    }
    var snapPayload = await getJson(endpoint("snapshot", "/api/local_sim/snapshot") + "?entities=0");
    var snapshot = snapPayload ? snapPayload.snapshot : null;

    var assertions = [];

    // patches -> patch_contains
    var patches = last.patches || [];
    for (var i = 0; i < patches.length; i++) {
      var p = patches[i] || {};
      var op = String(p.op || "");
      if (!op) continue;
      if (op === "switch_layout") {
        assertions.push({ type: "patch_contains", op: "switch_layout", layout_index: parseInt(p.layout_index, 10) || 0 });
        continue;
      }
      if (op === "set_widget_state" && p.ui_key && (typeof p.visible === "boolean")) {
        assertions.push({ type: "patch_contains", op: "set_widget_state", ui_key_contains: String(p.ui_key), visible: !!p.visible });
        continue;
      }
    }

    // diff_changes -> path_equals (graph_variables/lv) capped
    var changes = last.diff_changes || [];
    var cap = 30;
    for (var j = 0; j < changes.length && assertions.length < (cap + 60); j++) {
      var c = changes[j] || {};
      var dot = pointerToDotPath(c.path, snapshot);
      if (!dot) continue;
      if (dot.indexOf("graph_variables.") !== 0 && dot.indexOf("lv.") !== 0) continue;
      if (c.op === "remove") continue;
      assertions.push({ type: "path_equals", path: dot, equals: c.after });
      if (assertions.length >= (cap + 60)) break;
    }

    var spec = { version: 1, assertions: assertions };
    setAssertionsSpecToBox(spec);
    if (outBox) outBox.value = "已从 last_action 提取断言：" + String(assertions.length) + " 条（可编辑后运行）。\n";
  }

  async function runAssertionsAgainstLast() {
    var outBox = $("assertionsOutBox");
    if (outBox) outBox.value = "正在运行断言...\n";

    var spec = getAssertionsSpecFromBox();
    if (spec.__error) {
      if (outBox) outBox.value = "断言 JSON 解析失败: " + String(spec.__error) + "\n";
      return;
    }
    var assertions = spec.assertions || [];
    if (!assertions.length) {
      if (outBox) outBox.value = "未提供断言（assertions 为空）。\n";
      return;
    }

    var lastPayload = await getJson(endpoint("last_action", "/api/local_sim/last_action"));
    var last = (lastPayload && lastPayload.last_action) ? lastPayload.last_action : null;
    if (!last) {
      if (outBox) outBox.value = "没有 last_action，先点击 UI 或发送信号。\n";
      return;
    }

    var needsSnapshot = false;
    for (var i = 0; i < assertions.length; i++) {
      if (String((assertions[i] || {}).type || "") === "path_equals") { needsSnapshot = true; break; }
    }
    var snapshot = null;
    if (needsSnapshot) {
      var snapPayload = await getJson(endpoint("snapshot", "/api/local_sim/snapshot") + "?entities=0");
      snapshot = snapPayload ? snapPayload.snapshot : null;
    }

    var pass = 0;
    var fail = 0;
    var lines = [];
    lines.push("【断言结果】");
    lines.push("- total=" + String(assertions.length));
    lines.push("- last_action=" + String(last.kind || "") + "@" + String(last.timestamp || ""));
    lines.push("");

    for (var j = 0; j < assertions.length; j++) {
      var a = assertions[j] || {};
      var afterAction = a.after_action;
      if (afterAction !== undefined && afterAction !== null) {
        var ai = parseInt(afterAction, 10);
        if (!isNaN(ai) && ai !== -1) {
          lines.push("[SKIP] " + String(a.type || "") + " :: after_action=" + String(ai) + "（monitor 只对最后动作评估）");
          continue;
        }
      }
      var r = evalAssertionAgainstLast(last, snapshot, a);
      var ok = !!(r && r.ok);
      if (ok) pass += 1;
      else fail += 1;
      lines.push((ok ? "[PASS] " : "[FAIL] ") + String(a.type || "") + " :: " + (r && r.message ? r.message : ""));
    }
    lines.push("");
    lines.push("【汇总】PASS=" + String(pass) + " FAIL=" + String(fail));
    outBox.value = lines.join("\n");
    outBox.scrollTop = 0;
  }

