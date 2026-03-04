(function () {
  var NS = (window && window.__LOCAL_SIM__) ? window.__LOCAL_SIM__ : {};
  var $ = function (id) { return document.getElementById(id); };

  var uiFrame = $("uiFrame");
  var stage = $("stage");
  var stageContainer = $("stageContainer");

  var statusSub = $("statusSub");
  var statusBadge = $("statusBadge");
  var layoutSelect = $("layoutSelect");
  var flattenToggle = $("flattenToggle");
  var kvSession = $("kvSession");

  var traceBox = $("traceBox");
  var entitiesBox = $("entitiesBox");

  var resPreset = $("resPreset");
  var resW = $("resW");
  var resH = $("resH");
  var fitToggle = $("fitToggle");
  var fitInfo = $("fitInfo");

  var traceCursor = 0;
  var currentLayoutIndex = 0;
  var flattenEnabled = false;
  var currentStageW = 1920;
  var currentStageH = 1080;
  var recordedActions = [];
  var recordingEnabled = false;
  var paused = false;
  var showLastActionRaw = false;
  var traceEventsCache = [];
  var lastRenderedActionKey = "";
  var watchPollTimer = 0;
  var watchRuntime = { spec: null, items: [], lastByPath: {}, lastTriggeredAt: 0 };

  function jsonSafeStringify(obj) {
    return JSON.stringify(obj, null, 2);
  }

  function clampInt(n, minV, maxV) {
    var v = parseInt(n, 10);
    if (isNaN(v)) v = 0;
    if (typeof minV === "number" && v < minV) v = minV;
    if (typeof maxV === "number" && v > maxV) v = maxV;
    return v;
  }

  function shortJson(value, maxLen) {
    var limit = clampInt(maxLen, 20, 2000) || 260;
    var text = "";
    try {
      if (value === undefined) return "undefined";
      if (value === null) return "null";
      if (typeof value === "string") text = value;
      else if (typeof value === "number" || typeof value === "boolean") text = String(value);
      else text = JSON.stringify(value);
    } catch (_e) {
      text = String(value);
    }
    if (!text) return "";
    if (text.length <= limit) return text;
    return text.slice(0, Math.max(0, limit - 1)) + "…";
  }

  function fmtTime(ts) {
    var t = (typeof ts === "number") ? ts : parseFloat(ts);
    if (!t || isNaN(t)) return "";
    try {
      return new Date(t * 1000).toLocaleString();
    } catch (_e) {
      return String(t);
    }
  }

  function setLastActionViewMode(raw) {
    showLastActionRaw = !!raw;
    var reportBox = $("lastActionReportBox");
    var rawBox = $("lastActionRawBox");
    var btn = $("btnToggleLastActionRaw");
    if (reportBox) reportBox.style.display = showLastActionRaw ? "none" : "";
    if (rawBox) rawBox.style.display = showLastActionRaw ? "" : "none";
    if (btn) btn.textContent = showLastActionRaw ? "动作报告" : "原始JSON";
    try {
      if (window.localStorage) window.localStorage.setItem("ayaya_local_sim_last_action_raw", showLastActionRaw ? "1" : "0");
    } catch (_e) {
      // ignore
    }
  }

  function loadLastActionViewMode() {
    try {
      var v = window.localStorage ? window.localStorage.getItem("ayaya_local_sim_last_action_raw") : "";
      if (v !== null && v !== undefined && String(v) !== "") {
        setLastActionViewMode(String(v).trim() === "1");
        return;
      }
    } catch (_e) {
      // ignore
    }
    setLastActionViewMode(false);
  }

  function buildPatchLines(patches) {
    var items = patches || [];
    var out = { switch_layout: [], widget_state: [], group: [], other: [] };
    for (var i = 0; i < items.length; i++) {
      var p = items[i] || {};
      var op = String(p.op || "");
      if (op === "switch_layout") {
        out.switch_layout.push("  - switch_layout: layout_index=" + String(p.layout_index || ""));
        continue;
      }
      if (op === "set_widget_state") {
        var key = String(p.ui_key || p.widget_index || "");
        var vis = (p.visible === true) ? "true" : (p.visible === false ? "false" : "");
        var st = String(p.state || "");
        var hint = "";
        if (String(p.ui_state_group_key || "") && String(p.ui_state || "")) {
          hint = " (" + String(p.ui_state_group_key) + "." + String(p.ui_state) + ")";
        }
        out.widget_state.push("  - set_widget_state: " + key + hint + (st ? (" state=" + st) : "") + (vis ? (" visible=" + vis) : ""));
        continue;
      }
      if (op === "activate_widget_group" || op === "remove_widget_group") {
        var gk = String(p.ui_key || p.group_index || "");
        out.group.push("  - " + op + ": " + gk);
        continue;
      }
      out.other.push("  - " + (op || "unknown") + ": " + shortJson(p, 320));
    }
    return out;
  }

  function groupDiffChanges(changes) {
    var items = changes || [];
    var groups = { custom_variables: [], graph_variables: [], local_variables: [], ui: [], mounted_graphs: [], other: [] };
    for (var i = 0; i < items.length; i++) {
      var c = items[i] || {};
      var path = String(c.path || "");
      if (path.indexOf("/variables/custom_variables") === 0) {
        groups.custom_variables.push(c);
        continue;
      }
      if (path.indexOf("/variables/graph_variables") === 0) {
        groups.graph_variables.push(c);
        continue;
      }
      if (path.indexOf("/variables/local_variables") === 0) {
        groups.local_variables.push(c);
        continue;
      }
      if (path.indexOf("/ui/") === 0) {
        groups.ui.push(c);
        continue;
      }
      if (path.indexOf("/mounted_graphs") === 0) {
        groups.mounted_graphs.push(c);
        continue;
      }
      groups.other.push(c);
    }
    return groups;
  }

  function formatDiffLines(items, maxLines) {
    var limit = clampInt(maxLines, 5, 300) || 80;
    var out = [];
    for (var i = 0; i < items.length && i < limit; i++) {
      var c = items[i] || {};
      var op = String(c.op || "");
      var path = String(c.path || "");
      var before = shortJson(c.before, 220);
      var after = shortJson(c.after, 220);
      if (op === "add") out.push("  - add    " + path + " = " + after);
      else if (op === "remove") out.push("  - remove " + path + " (was " + before + ")");
      else out.push("  - replace " + path + ": " + before + " -> " + after);
    }
    if (items.length > limit) out.push("  ...（已截断 " + String(items.length - limit) + " 条）");
    return out;
  }

  function cacheTraceEvents(evs) {
    if (!evs || !evs.length) return;
    for (var i = 0; i < evs.length; i++) traceEventsCache.push(evs[i]);
    // cap memory
    var maxKeep = 5000;
    if (traceEventsCache.length > maxKeep) {
      traceEventsCache = traceEventsCache.slice(traceEventsCache.length - maxKeep);
    }
  }

  function formatTraceLine(e) {
    var ts = (e && typeof e.timestamp === "number") ? ("[" + String(e.timestamp.toFixed ? e.timestamp.toFixed(3) : e.timestamp) + "] ") : "";
    var kindRaw = (e && e.kind) ? String(e.kind) : "event";
    var kind = formatTraceKind(kindRaw);
    var msg = (e && e.message) ? (": " + String(e.message)) : "";
    var details = (e && e.details) ? (" " + shortJson(e.details, 260)) : "";
    return ts + kind + msg + details;
  }

  function buildTraceSnippetForAction(action) {
    if (!action || typeof action !== "object") return [];
    var ts = action.timestamp;
    if (typeof ts !== "number") ts = parseFloat(ts);
    if (!ts || isNaN(ts)) return [];
    var start = ts - 0.05;
    var end = ts + 2.0;
    var out = [];
    for (var i = 0; i < traceEventsCache.length; i++) {
      var e = traceEventsCache[i] || {};
      var et = (typeof e.timestamp === "number") ? e.timestamp : parseFloat(e.timestamp);
      if (!et || isNaN(et)) continue;
      if (et < start || et > end) continue;
      out.push("  - " + formatTraceLine(e));
      if (out.length >= 80) {
        out.push("  ...（已截断，建议看右侧 Trace 全量）");
        break;
      }
    }
    return out;
  }

  function buildActionReport(action) {
    if (!action) return "";
    var kind = String(action.kind || "");
    var input = action.input || {};
    var patches = action.patches || [];
    var diffSummary = action.diff_summary || {};
    var diffChanges = action.diff_changes || [];

    var lines = [];
    lines.push("【动作报告】");
    lines.push("- kind: " + (kind || "<unknown>"));
    if (typeof action.timestamp !== "undefined") lines.push("- timestamp: " + String(action.timestamp) + (fmtTime(action.timestamp) ? (" (" + fmtTime(action.timestamp) + ")") : ""));
    if (typeof action.duration_ms !== "undefined") lines.push("- duration_ms: " + String(action.duration_ms));

    if (kind === "ui_click") {
      lines.push("");
      lines.push("【输入】UI 点击");
      lines.push("- data_ui_key: " + String(input.data_ui_key || ""));
      lines.push("- data_ui_state_group: " + String(input.data_ui_state_group || ""));
      lines.push("- data_ui_state: " + String(input.data_ui_state || ""));
      lines.push("- chosen_ui_key: " + String(input.chosen_ui_key || ""));
      lines.push("- index: " + String(input.index || ""));
      lines.push("- player: " + String(input.player_entity_name || "") + " (" + String(input.player_entity_id || "") + ")");
    } else if (kind === "emit_signal") {
      lines.push("");
      lines.push("【输入】发送信号");
      lines.push("- signal_id: " + String((input && input.signal_id) || ""));
      lines.push("- resolved_signal_id: " + String((input && input.resolved_signal_id) || ""));
      lines.push("- params: " + shortJson((input && input.params) || {}, 600));
    } else {
      lines.push("");
      lines.push("【输入】");
      lines.push(shortJson(input, 1200));
    }

    lines.push("");
    lines.push("【UI patches】count=" + String((patches && patches.length) ? patches.length : 0));
    var p = buildPatchLines(patches);
    if (p.switch_layout.length) { lines.push("- switch_layout"); lines = lines.concat(p.switch_layout); }
    if (p.widget_state.length) { lines.push("- set_widget_state"); lines = lines.concat(p.widget_state); }
    if (p.group.length) { lines.push("- groups"); lines = lines.concat(p.group); }
    if (p.other.length) { lines.push("- other"); lines = lines.concat(p.other); }
    if (!p.switch_layout.length && !p.widget_state.length && !p.group.length && !p.other.length) lines.push("  （无）");

    lines.push("");
    lines.push("【数据 diff】" + " total=" + String(diffSummary.total || 0) + " add=" + String(diffSummary.add || 0) + " remove=" + String(diffSummary.remove || 0) + " replace=" + String(diffSummary.replace || 0));
    var g = groupDiffChanges(diffChanges);
    function _emitGroup(name, items) {
      if (!items || !items.length) return;
      lines.push("- " + name + " (" + String(items.length) + ")");
      lines = lines.concat(formatDiffLines(items, 60));
    }
    _emitGroup("custom_variables", g.custom_variables);
    _emitGroup("graph_variables", g.graph_variables);
    _emitGroup("ui", g.ui);
    _emitGroup("local_variables", g.local_variables);
    _emitGroup("mounted_graphs", g.mounted_graphs);
    _emitGroup("other", g.other);
    if ((!diffChanges) || !diffChanges.length) lines.push("  （无变化 / 未捕获）");

    lines.push("");
    lines.push("【关联 trace】(timestamp±2s)");
    var snippet = buildTraceSnippetForAction(action);
    if (snippet.length) lines = lines.concat(snippet);
    else lines.push("  （未命中：可能 trace 尚未拉取到这段时间窗，或该动作未触发 trace）");

    lines.push("");
    lines.push("提示：若要分享复现，请使用右下角「导出复现包」按钮。");
    return lines.join("\n");
  }

  function parseJsonText(text) {
    var raw = String(text || "").trim();
    if (!raw) return null;
    return JSON.parse(raw);
  }

  function normalizeAssertionsSpec(spec) {
    if (!spec) return { version: 1, assertions: [] };
    if (Array.isArray(spec)) return { version: 1, assertions: spec };
    if (typeof spec === "object") {
      var v = (typeof spec.version === "number") ? spec.version : 1;
      var arr = spec.assertions;
      if (!Array.isArray(arr)) arr = [];
      return { version: v, assertions: arr };
    }
    return { version: 1, assertions: [] };
  }

  function watchTemplate() {
    return {
      version: 1,
      poll_ms: 800,
      watches: [
        { path: "graph_variables.门_运动目标状态", break_on_change: true },
        { path: "lv.UI战斗_文本.对话", equals: "你好", break_on_equals: true },
        { path: "ui.ui_current_layout_by_player", break_on_change: false }
      ]
    };
  }

  function normalizeWatchSpec(spec) {
    if (!spec || typeof spec !== "object") return { version: 1, poll_ms: 800, watches: [] };
    var v = (typeof spec.version === "number") ? spec.version : 1;
    var pollMs = clampInt(spec.poll_ms, 200, 5000) || 800;
    var watches = Array.isArray(spec.watches) ? spec.watches : [];
    return { version: v, poll_ms: pollMs, watches: watches };
  }

  function getWatchSpecFromBox() {
    var box = $("watchBox");
    if (!box) return { version: 1, poll_ms: 800, watches: [] };
    var obj = null;
    try { obj = parseJsonText(box.value); } catch (e) { return { __error: String(e && e.message ? e.message : e) }; }
    return normalizeWatchSpec(obj);
  }

  function setWatchSpecToBox(spec) {
    var box = $("watchBox");
    if (!box) return;
    box.value = jsonSafeStringify(spec || { version: 1, poll_ms: 800, watches: [] });
    box.scrollTop = 0;
  }

  function stopWatchPolling() {
    if (watchPollTimer) {
      clearInterval(watchPollTimer);
      watchPollTimer = 0;
    }
  }

  async function pauseWorld(reason) {
    if (paused) return;
    try {
      await postJson(endpoint("pause", "/api/local_sim/pause"), { paused: true });
      await refreshStatus();
      var box = $("watchOutBox");
      if (box) {
        box.value = (box.value || "") + "\n[breakpoint] 已自动暂停：" + String(reason || "") + "\n";
        box.scrollTop = box.scrollHeight;
      }
    } catch (_e) {
      // ignore
    }
  }

  async function pollWatchOnce() {
    var box = $("watchOutBox");
    if (!box) return;

    var spec = watchRuntime.spec;
    var items = watchRuntime.items || [];
    if (!spec || !items.length) return;

    var snapPayload = null;
    try {
      snapPayload = await getJson(endpoint("snapshot", "/api/local_sim/snapshot") + "?entities=0");
    } catch (e) {
      box.value = "watch: snapshot 拉取失败: " + String(e && e.message ? e.message : e);
      return;
    }
    var snapshot = snapPayload ? snapPayload.snapshot : null;

    var out = [];
    out.push("【Watch】items=" + String(items.length) + " poll_ms=" + String(spec.poll_ms));
    out.push("paused=" + String(paused));
    out.push("");

    var triggered = false;
    var triggeredReason = "";
    for (var i = 0; i < items.length; i++) {
      var w = items[i] || {};
      var path = String(w.path || "");
      if (!path) continue;
      var r = getSnapshotPath(snapshot, path);
      var ok = !!r.ok;
      var val = ok ? r.value : undefined;
      var last = watchRuntime.lastByPath.hasOwnProperty(path) ? watchRuntime.lastByPath[path] : { has: false, value: undefined };

      var changed = false;
      if (!last.has) changed = true;
      else changed = !deepEqual(last.value, val);

      watchRuntime.lastByPath[path] = { has: true, value: val };

      var line = "- " + path + " = " + (ok ? shortJson(val, 220) : ("<err> " + String(r.error || "")));
      if (changed) line += "  [changed]";
      out.push(line);

      var breakOnChange = !!w.break_on_change;
      var breakOnEquals = !!w.break_on_equals;
      var hasEquals = (typeof w.equals !== "undefined");
      if (!paused) {
        if (!triggered && breakOnChange && changed) {
          triggered = true;
          triggeredReason = path + " changed";
        }
        if (!triggered && breakOnEquals && hasEquals) {
          if (deepEqual(val, w.equals)) {
            triggered = true;
            triggeredReason = path + " equals " + shortJson(w.equals, 160);
          }
        }
      }
    }

    box.value = out.join("\n");
    box.scrollTop = 0;

    // avoid spamming pause calls in tight loops
    if (triggered && !paused) {
      var now = Date.now();
      if (!watchRuntime.lastTriggeredAt || (now - watchRuntime.lastTriggeredAt > 800)) {
        watchRuntime.lastTriggeredAt = now;
        await pauseWorld(triggeredReason);
      }
    }
  }

  function applyWatchSpec() {
    var outBox = $("watchOutBox");
    if (outBox) outBox.value = "正在应用 watch...\n";

    var spec = getWatchSpecFromBox();
    if (spec.__error) {
      if (outBox) outBox.value = "watch JSON 解析失败: " + String(spec.__error) + "\n";
      return;
    }
    var watches = Array.isArray(spec.watches) ? spec.watches : [];
    var items = [];
    for (var i = 0; i < watches.length; i++) {
      var w = watches[i] || {};
      var path = String(w.path || "").trim();
      if (!path) continue;
      items.push({
        path: path,
        break_on_change: !!w.break_on_change,
        break_on_equals: !!w.break_on_equals,
        equals: w.equals
      });
    }
    watchRuntime.spec = spec;
    watchRuntime.items = items;
    watchRuntime.lastByPath = {};
    watchRuntime.lastTriggeredAt = 0;

    stopWatchPolling();
    if (!items.length) {
      if (outBox) outBox.value = "watch 为空：未启动轮询。\n";
      return;
    }

    // first poll immediately
    pollWatchOnce();
    watchPollTimer = setInterval(function () { pollWatchOnce(); }, clampInt(spec.poll_ms, 200, 5000) || 800);
    if (outBox) outBox.value = "watch 已启动：items=" + String(items.length) + "。\n";
  }

  function clearWatchAll() {
    stopWatchPolling();
    watchRuntime.spec = null;
    watchRuntime.items = [];
    watchRuntime.lastByPath = {};
    watchRuntime.lastTriggeredAt = 0;
    var outBox = $("watchOutBox");
    if (outBox) outBox.value = "";
  }

  function setAssertionsSpecToBox(spec) {
    var box = $("assertionsBox");
    if (!box) return;
    box.value = jsonSafeStringify(spec || { version: 1, assertions: [] });
    box.scrollTop = 0;
  }

  function getAssertionsSpecFromBox() {
    var box = $("assertionsBox");
    if (!box) return { version: 1, assertions: [] };
    var obj = null;
    try { obj = parseJsonText(box.value); } catch (e) { return { __error: String(e && e.message ? e.message : e) }; }
    return normalizeAssertionsSpec(obj);
  }

  function assertionsTemplate() {
    return {
      version: 1,
      note: "assertions are evaluated against LAST ACTION in monitor (pytest generator uses recorded actions + after_action optionally)",
      assertions: [
        { type: "patch_contains", op: "set_widget_state", ui_key_contains: "UI_STATE_GROUP__", visible: true },
        { type: "path_equals", path: "graph_variables.某变量名", equals: 1 },
        { type: "path_equals", path: "lv.UI战斗_文本.对话", equals: "你好" },
        { type: "trace_contains", kind: "event_dispatch", message_contains: "实体创建时" }
      ]
    };
  }

  function deepEqual(a, b) {
    if (a === b) return true;
    if (a === null || a === undefined || b === null || b === undefined) return a === b;
    if (typeof a !== typeof b) return false;
    if (typeof a !== "object") return a === b;
    if (Array.isArray(a)) {
      if (!Array.isArray(b)) return false;
      if (a.length !== b.length) return false;
      for (var i = 0; i < a.length; i++) if (!deepEqual(a[i], b[i])) return false;
      return true;
    }
    if (Array.isArray(b)) return false;
    var aKeys = [];
    for (var k in a) if (Object.prototype.hasOwnProperty.call(a, k)) aKeys.push(k);
    var bKeys = [];
    for (var k2 in b) if (Object.prototype.hasOwnProperty.call(b, k2)) bKeys.push(k2);
    if (aKeys.length !== bKeys.length) return false;
    aKeys.sort();
    bKeys.sort();
    for (var j = 0; j < aKeys.length; j++) if (aKeys[j] !== bKeys[j]) return false;
    for (var j2 = 0; j2 < aKeys.length; j2++) {
      var key = aKeys[j2];
      if (!deepEqual(a[key], b[key])) return false;
    }
    return true;
  }

