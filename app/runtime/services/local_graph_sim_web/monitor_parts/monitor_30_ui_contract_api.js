  function getQueryParam(name) {
    if (NS && typeof NS.getQueryParam === "function") return String(NS.getQueryParam(name) || "");
    var sp = new URLSearchParams(String(window.location && window.location.search ? window.location.search : ""));
    return String(sp.get(String(name || "")) || "");
  }

  function isTruthyParam(raw) {
    if (NS && typeof NS.isTruthyParam === "function") return !!NS.isTruthyParam(raw);
    var t = String(raw || "").trim().toLowerCase();
    return t === "1" || t === "true" || t === "yes" || t === "on";
  }

  function endpoint(name, fallback) {
    if (NS && typeof NS.endpoint === "function") return String(NS.endpoint(name, fallback) || "");
    return String(fallback || "");
  }

  function getIframeDoc() {
    try {
      if (!uiFrame) return null;
      return uiFrame.contentDocument || (uiFrame.contentWindow ? uiFrame.contentWindow.document : null);
    } catch (_e) {
      return null;
    }
  }

  function attrFrom(el, name) {
    if (!el || !el.getAttribute) return "";
    var v = el.getAttribute(name);
    return (v === null || v === undefined) ? "" : String(v);
  }

  function trim(text) {
    return String(text || "").replace(/^\s+|\s+$/g, "");
  }

  function nearestAttrFrom(el, name, maxDepth) {
    var limit = clampInt(maxDepth, 1, 20) || 12;
    var cur = el;
    var d = 0;
    while (cur && cur.getAttribute && d < limit) {
      var v = trim(attrFrom(cur, name));
      if (v) return v;
      cur = cur.parentElement;
      d += 1;
    }
    return "";
  }

  function uniqByKey(items, keyFn) {
    var out = [];
    var seen = {};
    for (var i = 0; i < (items || []).length; i++) {
      var it = items[i];
      var k = String(keyFn(it) || "");
      if (!k) continue;
      if (seen[k]) continue;
      seen[k] = 1;
      out.push(it);
    }
    return out;
  }

  async function resolveUiKeyOnce(payload) {
    var url = endpoint("resolve_ui_key", "/api/local_sim/resolve_ui_key");
    return await postJson(url, payload || {});
  }

  async function runUiContractCheck() {
    var box = $("uiContractBox");
    if (!box) return;
    box.value = "正在扫描 UI...\n";

    var doc = getIframeDoc();
    if (!doc || !doc.querySelectorAll) {
      box.value += "无法访问 iframe DOM（UI 可能还未加载完成）。请先点击「刷新预览」，然后重试。\n";
      return;
    }

    var lines = [];
    lines.push("【UI 合约检查】");

    // 1) Buttons
    var btnEls = [];
    try { btnEls = doc.querySelectorAll('[data-ui-role="button"][data-ui-key]') || []; } catch (_e1) { btnEls = []; }
    var btnItems = [];
    for (var i = 0; i < btnEls.length; i++) {
      var el = btnEls[i];
      var key = trim(attrFrom(el, "data-ui-key"));
      if (!key) continue;
      var sg = nearestAttrFrom(el, "data-ui-state-group", 12);
      var st = nearestAttrFrom(el, "data-ui-state", 12);
      btnItems.push({ data_ui_key: key, data_ui_state_group: sg, data_ui_state: st });
    }
    btnItems = uniqByKey(btnItems, function (x) { return (x.data_ui_key || "") + "||" + (x.data_ui_state_group || "") + "||" + (x.data_ui_state || ""); });

    lines.push("");
    lines.push("【按钮】[data-ui-role=\"button\"] total=" + String(btnItems.length));

    var resolvedBtn = 0;
    var unresolvedBtn = [];
    for (var b = 0; b < btnItems.length; b++) {
      var item = btnItems[b];
      try {
        var r = await resolveUiKeyOnce(item);
        if (r && r.ok && r.resolved) {
          resolvedBtn += 1;
        } else {
          unresolvedBtn.push(item);
        }
      } catch (_e2) {
        unresolvedBtn.push(item);
      }
    }
    lines.push("- resolvable: " + String(resolvedBtn));
    lines.push("- unresolved: " + String(unresolvedBtn.length));
    if (unresolvedBtn.length) {
      for (var ub = 0; ub < unresolvedBtn.length && ub < 60; ub++) {
        var u = unresolvedBtn[ub];
        lines.push("  - " + String(u.data_ui_key) + " (group=" + String(u.data_ui_state_group || "") + ", state=" + String(u.data_ui_state || "") + ")");
      }
      if (unresolvedBtn.length > 60) lines.push("  ...（已截断）");
    }

    // 2) State groups coverage -> UI_STATE_GROUP__<group>__<state>__group exists in registry
    var statePairs = [];
    var direct = [];
    try { direct = doc.querySelectorAll('[data-ui-state-group][data-ui-state]') || []; } catch (_e3) { direct = []; }
    for (var di = 0; di < direct.length; di++) {
      var el2 = direct[di];
      var gk = trim(attrFrom(el2, "data-ui-state-group"));
      var sk = trim(attrFrom(el2, "data-ui-state"));
      if (gk && sk) statePairs.push({ group: gk, state: sk });
    }
    var containers = [];
    try { containers = doc.querySelectorAll('[data-ui-state-group]') || []; } catch (_e4) { containers = []; }
    for (var ci = 0; ci < containers.length; ci++) {
      var c = containers[ci];
      var cg = trim(attrFrom(c, "data-ui-state-group"));
      if (!cg) continue;
      var children = c.children || [];
      for (var cj = 0; cj < children.length; cj++) {
        var ch = children[cj];
        var cs = trim(attrFrom(ch, "data-ui-state"));
        if (cs) statePairs.push({ group: cg, state: cs });
      }
    }
    statePairs = uniqByKey(statePairs, function (x) { return (x.group || "") + "||" + (x.state || ""); });

    lines.push("");
    lines.push("【状态组】[data-ui-state-group/state] total=" + String(statePairs.length));

    var resolvedStates = 0;
    var unresolvedStates = [];
    for (var si = 0; si < statePairs.length; si++) {
      var sp = statePairs[si];
      var fullKey = "UI_STATE_GROUP__" + String(sp.group) + "__" + String(sp.state) + "__group";
      try {
        var rr = await resolveUiKeyOnce({ data_ui_key: fullKey, data_ui_state_group: "", data_ui_state: "" });
        if (rr && rr.ok && rr.resolved) resolvedStates += 1;
        else unresolvedStates.push(sp);
      } catch (_e5) {
        unresolvedStates.push(sp);
      }
    }
    lines.push("- registry_covered: " + String(resolvedStates));
    lines.push("- missing_in_registry: " + String(unresolvedStates.length));
    if (unresolvedStates.length) {
      for (var ms = 0; ms < unresolvedStates.length && ms < 60; ms++) {
        var m2 = unresolvedStates[ms];
        lines.push("  - group=" + String(m2.group) + " state=" + String(m2.state));
      }
      if (unresolvedStates.length > 60) lines.push("  ...（已截断）");
    }

    // 3) data-ui-text bindings coverage (lv.*)
    var textEls = [];
    try { textEls = doc.querySelectorAll('[data-ui-text]') || []; } catch (_e6) { textEls = []; }
    var lvExprs = [];
    var lvRootVars = [];
    var re = /\{(\d+):([^}]+)\}/g;
    for (var ti = 0; ti < textEls.length; ti++) {
      var tpl = trim(attrFrom(textEls[ti], "data-ui-text"));
      if (!tpl) continue;
      var m;
      while ((m = re.exec(tpl)) !== null) {
        var expr = trim(m[2] || "");
        if (expr.indexOf("lv.") === 0) {
          var rest = expr.slice(3);
          lvExprs.push("lv." + rest);
          var parts = rest.split(".");
          var root = trim(parts[0] || "");
          if (root) lvRootVars.push(root);
        }
      }
    }
    lvExprs = uniqByKey(lvExprs, function (x) { return x; });
    lvRootVars = uniqByKey(lvRootVars, function (x) { return x; });

    var stPayload = null;
    try { stPayload = await getJson(endpoint("status", "/api/local_sim/status")); } catch (_e7) { stPayload = null; }
    var lvDefaultKeys = [];
    if (stPayload && stPayload.sim_notes && stPayload.sim_notes.ui_lv_defaults_keys) {
      lvDefaultKeys = stPayload.sim_notes.ui_lv_defaults_keys || [];
    }
    var defaultKeyMap = {};
    for (var dk = 0; dk < lvDefaultKeys.length; dk++) defaultKeyMap[String(lvDefaultKeys[dk] || "")] = 1;

    lines.push("");
    lines.push("【绑定】[data-ui-text] lv.* expr=" + String(lvExprs.length) + " root_vars=" + String(lvRootVars.length));
    if (!lvRootVars.length) {
      lines.push("- 未检测到 lv.* 模板绑定");
    } else {
      var missingLv = [];
      for (var rv = 0; rv < lvRootVars.length; rv++) {
        var k2 = String(lvRootVars[rv]);
        if (!defaultKeyMap[k2]) missingLv.push(k2);
      }
      lines.push("- ui_lv_defaults_keys: " + String(lvDefaultKeys.length));
      lines.push("- roots_missing_in_defaults: " + String(missingLv.length));
      if (missingLv.length) {
        for (var mi3 = 0; mi3 < missingLv.length && mi3 < 60; mi3++) lines.push("  - " + String(missingLv[mi3]));
        if (missingLv.length > 60) lines.push("  ...（已截断）");
      }
    }

    // verdict
    lines.push("");
    var ok = (unresolvedBtn.length === 0) && (unresolvedStates.length === 0);
    lines.push("【结果】" + (ok ? "PASS（按钮/状态组可解析）" : "FAIL（存在不可解析项）"));
    if (!ok) lines.push("提示：优先修复 unresolved 按钮与 missing_in_registry 的状态组；否则 click/patch 可能无法闭环。");

    box.value = lines.join("\n");
    box.scrollTop = 0;
  }

  function ensureSchema(data) {
    var expected = 1;
    if (NS && typeof NS.getProtocol === "function") {
      var p = NS.getProtocol();
      if (p && typeof p.schema_version === "number") expected = p.schema_version;
    }
    var got = data ? data.schema_version : undefined;
    if (typeof got !== "number") {
      throw new Error("协议不兼容：响应缺少 schema_version");
    }
    if (got !== expected) {
      throw new Error("协议不兼容：schema_version=" + String(got) + "（期望 " + String(expected) + "）");
    }
  }

  async function getJson(url) {
    var resp = await fetch(url, { cache: "no-store" });
    var text = await resp.text();
    var data = text ? JSON.parse(text) : {};
    if (!resp.ok) { throw new Error("HTTP " + resp.status + " " + text); }
    ensureSchema(data);
    return data;
  }

  async function postJson(url, body) {
    var resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      cache: "no-store",
    });
    var text = await resp.text();
    var data = text ? JSON.parse(text) : {};
    if (!resp.ok) { throw new Error("HTTP " + resp.status + " " + text); }
    ensureSchema(data);
    return data;
  }

