(function () {
  var API_CLICK = "/api/local_sim/click";
  var API_STATUS = "/api/local_sim/status";
  var API_BOOTSTRAP = "/api/local_sim/bootstrap";
  var API_SYNC = "/api/local_sim/sync";
  var API_POLL = "/api/local_sim/poll";

  function _trim(text) {
    return String(text || "").replace(/^\s+|\s+$/g, "");
  }

  function qsa(sel) {
    var items = document.querySelectorAll(sel);
    var out = [];
    for (var i = 0; i < items.length; i++) out.push(items[i]);
    return out;
  }

  function attr(el, name) {
    if (!el || !el.getAttribute) return "";
    return String(el.getAttribute(name) || "");
  }

  function nearestAttr(el, name) {
    var cur = el;
    while (cur) {
      var v = _trim(attr(cur, name));
      if (v) return v;
      cur = cur.parentElement;
    }
    return "";
  }

  function ensureBadge() {
    var existing = document.getElementById("local-sim-badge");
    if (existing) return existing;

    var badge = document.createElement("div");
    badge.id = "local-sim-badge";
    badge.style.position = "fixed";
    badge.style.right = "12px";
    badge.style.bottom = "12px";
    badge.style.zIndex = "2147483647";
    badge.style.pointerEvents = "none";
    badge.style.maxWidth = "60vw";
    badge.style.padding = "6px 10px";
    badge.style.borderRadius = "8px";
    badge.style.fontSize = "12px";
    badge.style.fontFamily = "Consolas, Menlo, monospace";
    badge.style.color = "#fff";
    badge.style.background = "rgba(0,0,0,0.65)";
    badge.style.border = "1px solid rgba(255,255,255,0.15)";
    badge.style.whiteSpace = "pre-wrap";
    badge.textContent = "[local_sim] ready";
    document.body.appendChild(badge);
    return badge;
  }

  function setBadge(text) {
    var badge = ensureBadge();
    badge.textContent = "[local_sim] " + String(text || "");
  }

  function _getQueryParam(name) {
    var s = String(window.location.search || "");
    var m = s.match(new RegExp("[?&]" + String(name || "") + "=([^&]+)"));
    if (!m) return "";
    return String(m[1] || "");
  }

  function requestSwitchLayout(layoutIndex) {
    var idxText = String(layoutIndex || "").replace(/^\s+|\s+$/g, "");
    if (!idxText) return;
    var cur = _getQueryParam("layout");
    if (cur === idxText) return;

    if (window.parent && window.parent !== window && typeof window.parent.__localSimSetLayout === "function") {
      window.parent.__localSimSetLayout(parseInt(idxText, 10) || 0);
      return;
    }

    window.location.href = "/ui.html?layout=" + encodeURIComponent(idxText);
  }

  function applyCanvasSizeVars() {
    var w = window.innerWidth || 0;
    var h = window.innerHeight || 0;
    if (!w || !h) return;
    if (!document || !document.documentElement || !document.documentElement.style) return;
    document.documentElement.style.setProperty("--canvas-width", String(w) + "px");
    document.documentElement.style.setProperty("--canvas-height", String(h) + "px");
  }
  applyCanvasSizeVars();
  if (window.addEventListener) {
    window.addEventListener("resize", applyCanvasSizeVars, false);
  }

  // base(data-ui-key) -> data-ui-state-group（用于 UI_STATE_GROUP 别名回映射）
  var baseToStateGroup = {};
  var baseEls = qsa("[data-ui-key][data-ui-state-group]");
  for (var iBase = 0; iBase < baseEls.length; iBase++) {
    var elBase = baseEls[iBase];
    var baseKey = _trim(attr(elBase, "data-ui-key"));
    var groupKey = _trim(attr(elBase, "data-ui-state-group"));
    if (baseKey && groupKey && !baseToStateGroup.hasOwnProperty(baseKey)) {
      baseToStateGroup[baseKey] = groupKey;
    }
  }

  function parseUiStateGroupKey(uiKey) {
    var text = _trim(uiKey);
    if (text.indexOf("UI_STATE_GROUP__") !== 0) return null;
    var parts = text.split("__");
    if (parts.length < 4) return null;
    return { base: parts[1] || "", state: parts[2] || "" };
  }

  function setStateGroupVisible(groupAttr, stateName, visible) {
    if (!groupAttr || !stateName) return;

    // 重要：同一个 state_group 可能同时存在两种结构：
    // - Pattern A: 每个状态元素自身携带 data-ui-state-group + data-ui-state（常见于按钮 enabled/disabled、highlight marker）
    // - Pattern B: 容器携带 data-ui-state-group，状态元素是其直接子元素（常见于 overlay：tutorial_overlay/battle_settlement_overlay）
    //
    // 若仅“二选一”，会导致例如 tutorial_overlay 这种“marker(A) + overlay(B)”并存时，
    // A 先命中导致 B 永远不生效，从而出现“日志里切状态了，但页面没变化”的错觉。
    var members = [];

    // Pattern A
    var direct = document.querySelectorAll('[data-ui-state-group="' + groupAttr + '"][data-ui-state]');
    if (direct && direct.length) {
      for (var di = 0; di < direct.length; di++) members.push(direct[di]);
    }

    // Pattern B
    var containers = document.querySelectorAll('[data-ui-state-group="' + groupAttr + '"]');
    if (containers && containers.length) {
      for (var ci = 0; ci < containers.length; ci++) {
        var c = containers[ci];
        var children = c.children || [];
        for (var cj = 0; cj < children.length; cj++) {
          var child = children[cj];
          var stChild = _trim(attr(child, "data-ui-state"));
          if (stChild) members.push(child);
        }
      }
    }

    // 去重：避免同一个节点被重复处理（例如 state element 同时满足 A 与 B）
    var uniq = [];
    for (var ui = 0; ui < members.length; ui++) {
      var item = members[ui];
      if (!item) continue;
      var exists = false;
      for (var uj = 0; uj < uniq.length; uj++) {
        if (uniq[uj] === item) {
          exists = true;
          break;
        }
      }
      if (!exists) uniq.push(item);
    }
    members = uniq;

    if (!members || members.length === 0) return;

    if (visible) {
      for (var mi = 0; mi < members.length; mi++) {
        var m = members[mi];
        var st = _trim(attr(m, "data-ui-state"));
        if (!st) continue;
        if (st === stateName) {
          m.setAttribute("data-ui-state-default", "1");
        } else {
          m.removeAttribute("data-ui-state-default");
        }
      }
    } else {
      for (var mi2 = 0; mi2 < members.length; mi2++) {
        var m2 = members[mi2];
        var st2 = _trim(attr(m2, "data-ui-state"));
        if (st2 === stateName) {
          m2.removeAttribute("data-ui-state-default");
        }
      }
    }
  }

  function applyPatch(p) {
    if (!p || typeof p !== "object") return;
    var op = String(p.op || "");

    if (op === "set_widget_state") {
      var uiKey = String(p.ui_key || "");
      var parsed = parseUiStateGroupKey(uiKey);
      if (parsed) {
        var groupAttr = baseToStateGroup[parsed.base] || parsed.base;
        var visible = Boolean(p.visible);
        setStateGroupVisible(groupAttr, parsed.state, visible);
      }
      return;
    }

    if (op === "switch_layout") {
      var idx = p.layout_index;
      document.documentElement.setAttribute("data-local-sim-layout-index", String(idx || ""));
      setBadge("switch_layout -> " + String(idx || ""));
      requestSwitchLayout(idx);
      return;
    }

    if (op === "activate_widget_group") {
      setBadge("activate_widget_group: " + String(p.group_index || ""));
      return;
    }

    if (op === "remove_widget_group") {
      setBadge("remove_widget_group: " + String(p.group_index || ""));
      return;
    }
  }

  function _xhrJson(method, url, payload, cb) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader("Content-Type", "application/json; charset=utf-8");

    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      var status = xhr.status || 0;
      if (status < 200 || status >= 300) {
        cb("http_" + String(status), null);
        return;
      }
      var data = JSON.parse(xhr.responseText || "{}");
      cb(null, data);
    };

    xhr.onerror = function () {
      cb("network_error", null);
    };

    if (method === "GET") {
      xhr.send();
      return;
    }
    xhr.send(JSON.stringify(payload || {}));
  }

  function findRoleButtonTarget(target) {
    var cur = target;
    while (cur && cur.getAttribute) {
      var role = _trim(attr(cur, "data-ui-role"));
      var key = _trim(attr(cur, "data-ui-key"));
      if (role === "button" && key) return cur;
      cur = cur.parentElement;
    }
    return null;
  }

  function findRoleButtonTargetAtPoint(x, y) {
    if (typeof document.elementsFromPoint === "function") {
      var els = document.elementsFromPoint(x, y) || [];
      for (var i = 0; i < els.length; i++) {
        var cand = findRoleButtonTarget(els[i]);
        if (cand) return cand;
      }
    } else if (typeof document.elementFromPoint === "function") {
      var top = document.elementFromPoint(x, y);
      var cand2 = findRoleButtonTarget(top);
      if (cand2) return cand2;
    }
    return null;
  }

  function findRoleButtonTargetByRect(x, y) {
    var buttons = qsa('[data-ui-role="button"][data-ui-key]');
    var best = null;
    var bestArea = 0;
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      if (!b || !b.getBoundingClientRect) continue;
      var cs = window.getComputedStyle ? window.getComputedStyle(b) : null;
      if (cs && (cs.display === "none" || cs.visibility === "hidden")) continue;
      var r = b.getBoundingClientRect();
      if (!r) continue;
      if (x < r.left || x > r.right || y < r.top || y > r.bottom) continue;
      var area = Math.max(1, (r.right - r.left) * (r.bottom - r.top));
      if (!best || area < bestArea) {
        best = b;
        bestArea = area;
      }
    }
    return best;
  }

  function onDocumentClick(evt) {
    var e = evt || window.event;
    var rawTarget = e.target || e.srcElement;
    var el = findRoleButtonTarget(rawTarget);
    if (!el && typeof e.clientX === "number" && typeof e.clientY === "number") {
      el = findRoleButtonTargetAtPoint(e.clientX, e.clientY);
    }
    if (!el && typeof e.clientX === "number" && typeof e.clientY === "number") {
      el = findRoleButtonTargetByRect(e.clientX, e.clientY);
    }
    if (!el) return;

    var dataUiKey = _trim(attr(el, "data-ui-key"));
    var dataUiStateGroup = nearestAttr(el, "data-ui-state-group");
    var dataUiState = nearestAttr(el, "data-ui-state");
    if (!dataUiKey) return;

    setBadge("click: " + dataUiKey);

    var payload = {
      data_ui_key: dataUiKey,
      data_ui_state_group: String(dataUiStateGroup || ""),
      data_ui_state: String(dataUiState || ""),
    };

    _xhrJson("POST", API_CLICK, payload, function (err, resp) {
      if (err) {
        setBadge("click failed: " + String(err));
        return;
      }
      var patches = resp && resp.patches && resp.patches.length ? resp.patches : [];
      for (var pi = 0; pi < patches.length; pi++) applyPatch(patches[pi]);
      setBadge("patches: " + String(patches.length));
    });
  }

  window.__local_sim_apply_patches = function (patches) {
    var items = patches && patches.length ? patches : [];
    for (var i = 0; i < items.length; i++) applyPatch(items[i]);
  };

  if (document.addEventListener) {
    document.addEventListener("click", onDocumentClick, false);
  } else if (document.attachEvent) {
    document.attachEvent("onclick", onDocumentClick);
  }

  // status（可视化提示：避免用户误判“按钮点不了”）
  _xhrJson("GET", API_STATUS, null, function (err, s) {
    if (err) {
      setBadge("status error: " + String(err));
      return;
    }
    if (s && s.ok && s.graph && s.graph.graph_name) {
      setBadge("connected: " + String(s.graph.graph_name));
      return;
    }
    setBadge("connected");
  });

  // 启动补丁：用于 server 侧 auto_emit_signal 的首帧 UI 状态回显
  _xhrJson("GET", API_SYNC, null, function (err, resp) {
    if (err) {
      setBadge("sync error: " + String(err));
      return;
    }
    var patches = resp && resp.patches && resp.patches.length ? resp.patches : [];
    for (var pi = 0; pi < patches.length; pi++) applyPatch(patches[pi]);
    if (patches.length) setBadge("sync patches: " + String(patches.length));
  });

  // 兼容旧版：bootstrap 会 drain（用于“异步 auto_emit_signal”补丁回显）
  function pollBootstrap(triesLeft) {
    _xhrJson("GET", API_BOOTSTRAP, null, function (err, resp) {
      if (err) {
        setBadge("bootstrap error: " + String(err));
        return;
      }
      var patches = resp && resp.patches && resp.patches.length ? resp.patches : [];
      for (var pi = 0; pi < patches.length; pi++) applyPatch(patches[pi]);
      if (patches.length) {
        setBadge("bootstrap patches: " + String(patches.length));
        return;
      }
      if ((triesLeft || 0) <= 0) return;
      setTimeout(function () {
        pollBootstrap((triesLeft || 0) - 1);
      }, 450);
    });
  }
  pollBootstrap(20);

  // 轮询：推进定时器并同步 UI 文本绑定（倒计时等）
  var uiTextEls = qsa("[data-ui-text]");

  function _getPath(root, parts) {
    var cur = root;
    for (var i = 0; i < (parts || []).length; i++) {
      if (!cur || typeof cur !== "object") return undefined;
      var k = String(parts[i] || "");
      if (!k) return undefined;
      if (cur.hasOwnProperty && cur.hasOwnProperty(k)) {
        cur = cur[k];
      } else if (k in cur) {
        cur = cur[k];
      } else {
        return undefined;
      }
    }
    return cur;
  }

  function resolveBinding(expr, bindings) {
    var text = _trim(expr);
    if (!text) return "";
    var parts = text.split(".");
    if (!parts || parts.length < 2) return "";
    var rootKey = String(parts[0] || "");
    if (rootKey === "lv") {
      var lv = (bindings && bindings.lv && typeof bindings.lv === "object") ? bindings.lv : {};
      var v = _getPath(lv, parts.slice(1));
      if (v === undefined || v === null) return "";
      if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
      return JSON.stringify(v);
    }
    return "";
  }

  function renderTemplate(tpl, bindings) {
    var resolved = 0;
    var raw = String(tpl || "");
    var out = raw.replace(/\{(\d+):([^}]+)\}/g, function (_m, _idx, expr) {
      var v = resolveBinding(expr, bindings);
      var vText = (v === undefined || v === null) ? "" : String(v);
      if (vText !== "") resolved += 1;
      return vText;
    });
    return { text: out, resolved: resolved };
  }

  function applyBindings(bindings) {
    if (!bindings || !bindings.lv) return;
    var hasKey = false;
    for (var k in bindings.lv) {
      if (bindings.lv.hasOwnProperty && bindings.lv.hasOwnProperty(k)) {
        hasKey = true;
        break;
      }
    }
    if (!hasKey) return;
    for (var i = 0; i < uiTextEls.length; i++) {
      var el = uiTextEls[i];
      if (!el) continue;
      var tpl = el.__localSimTextTpl;
      if (!tpl) {
        tpl = attr(el, "data-ui-text");
        el.__localSimTextTpl = tpl;
      }
      if (!tpl) continue;
      var rendered = renderTemplate(tpl, bindings);
      if (!rendered || !rendered.resolved) continue; // 未解析出任何值：保留 HTML 自带示例文本
      var text = String(rendered.text || "");
      if (el.textContent !== text) el.textContent = text;
    }
  }

  // Workbench highlight marker（.highlight-display-area）在源码 HTML 中本体透明，
  // 压暗/挖空通常由“扁平化/导出”阶段生成 shadow layers。
  // 本地测试直接加载 UI源码，因此这里用 JS 在浏览器侧模拟 4 块阴影层。
  var _highlightDimRoot = null;
  var _highlightDimLayers = null;

  function ensureHighlightDim() {
    if (_highlightDimRoot && _highlightDimLayers) return;
    if (!document || !document.body) return;
    var root = document.getElementById("local-sim-highlight-dim");
    if (!root) {
      root = document.createElement("div");
      root.id = "local-sim-highlight-dim";
      root.style.position = "fixed";
      root.style.left = "0";
      root.style.top = "0";
      root.style.right = "0";
      root.style.bottom = "0";
      root.style.pointerEvents = "none";
      root.style.zIndex = "4999"; // 低于 tutorial_overlay(5000)，避免盖住教程卡片按钮
      root.style.display = "none";
      document.body.appendChild(root);
    }
    var layers = [];
    for (var i = 0; i < 4; i++) {
      var layer = document.createElement("div");
      layer.className = "local-sim-highlight-dim-layer";
      layer.style.position = "absolute";
      layer.style.left = "0";
      layer.style.top = "0";
      layer.style.width = "0";
      layer.style.height = "0";
      layer.style.background = "rgba(0,0,0,0.45)";
      layers.push(layer);
      root.appendChild(layer);
    }
    _highlightDimRoot = root;
    _highlightDimLayers = layers;
  }

  function _clamp(n, minV, maxV) {
    var v = (typeof n === "number") ? n : (parseFloat(n) || 0);
    if (v < minV) return minV;
    if (v > maxV) return maxV;
    return v;
  }

  function _isVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var cs = window.getComputedStyle ? window.getComputedStyle(el) : null;
    if (cs && (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0")) return false;
    var r = el.getBoundingClientRect();
    if (!r) return false;
    return (r.width > 1 && r.height > 1);
  }

  function _parseAlpha(el) {
    var raw = _trim(attr(el, "data-highlight-overlay-alpha"));
    var a = parseFloat(raw);
    if (!raw || isNaN(a)) a = 0.45;
    return _clamp(a, 0.0, 0.95);
  }

  function findActiveHighlightMarker() {
    var markers = qsa(".highlight-display-area");
    var best = null;
    var bestArea = 0;
    for (var i = 0; i < markers.length; i++) {
      var m = markers[i];
      if (!_isVisible(m)) continue;
      var r = m.getBoundingClientRect();
      var area = Math.max(0, (r.width || 0) * (r.height || 0));
      if (!best || area > bestArea) {
        best = m;
        bestArea = area;
      }
    }
    return best;
  }

  function updateHighlightDim() {
    ensureHighlightDim();
    if (!_highlightDimRoot || !_highlightDimLayers) return;

    var marker = findActiveHighlightMarker();
    if (!marker) {
      _highlightDimRoot.style.display = "none";
      return;
    }

    var w = window.innerWidth || 0;
    var h = window.innerHeight || 0;
    if (!w || !h) {
      _highlightDimRoot.style.display = "none";
      return;
    }

    var r = marker.getBoundingClientRect();
    var x1 = _clamp(r.left, 0, w);
    var y1 = _clamp(r.top, 0, h);
    var x2 = _clamp(r.right, 0, w);
    var y2 = _clamp(r.bottom, 0, h);
    if (x2 <= x1 || y2 <= y1) {
      _highlightDimRoot.style.display = "none";
      return;
    }

    var alpha = _parseAlpha(marker);
    var bg = "rgba(0,0,0," + String(alpha) + ")";
    _highlightDimRoot.style.display = "block";

    // top
    _highlightDimLayers[0].style.left = "0px";
    _highlightDimLayers[0].style.top = "0px";
    _highlightDimLayers[0].style.width = String(w) + "px";
    _highlightDimLayers[0].style.height = String(y1) + "px";
    _highlightDimLayers[0].style.background = bg;
    // bottom
    _highlightDimLayers[1].style.left = "0px";
    _highlightDimLayers[1].style.top = String(y2) + "px";
    _highlightDimLayers[1].style.width = String(w) + "px";
    _highlightDimLayers[1].style.height = String(Math.max(0, h - y2)) + "px";
    _highlightDimLayers[1].style.background = bg;
    // left
    _highlightDimLayers[2].style.left = "0px";
    _highlightDimLayers[2].style.top = String(y1) + "px";
    _highlightDimLayers[2].style.width = String(x1) + "px";
    _highlightDimLayers[2].style.height = String(Math.max(0, y2 - y1)) + "px";
    _highlightDimLayers[2].style.background = bg;
    // right
    _highlightDimLayers[3].style.left = String(x2) + "px";
    _highlightDimLayers[3].style.top = String(y1) + "px";
    _highlightDimLayers[3].style.width = String(Math.max(0, w - x2)) + "px";
    _highlightDimLayers[3].style.height = String(Math.max(0, y2 - y1)) + "px";
    _highlightDimLayers[3].style.background = bg;
  }

  if (window.addEventListener) {
    window.addEventListener("resize", function () {
      updateHighlightDim();
    }, false);
  }

  var _pollInFlight = false;
  function pollRuntime() {
    if (_pollInFlight) return;
    _pollInFlight = true;
    _xhrJson("GET", API_POLL, null, function (err, resp) {
      _pollInFlight = false;
      if (err) return;
      var patches = resp && resp.patches && resp.patches.length ? resp.patches : [];
      for (var pi = 0; pi < patches.length; pi++) applyPatch(patches[pi]);
      if (resp && resp.bindings) applyBindings(resp.bindings);
      updateHighlightDim();
      if (patches.length) setBadge("patches: " + String(patches.length));
    });
  }
  pollRuntime();
  setInterval(pollRuntime, 250);
})();
