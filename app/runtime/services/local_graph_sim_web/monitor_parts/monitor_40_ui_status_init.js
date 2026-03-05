  function setStatus(ok, text) {
    statusBadge.textContent = ok ? "在线" : "离线";
    statusBadge.style.borderColor = ok ? "rgba(90,162,255,.45)" : "rgba(255,255,255,.10)";
    statusBadge.style.color = ok ? "rgba(90,162,255,.95)" : "rgba(255,255,255,.55)";
    statusSub.textContent = text || (ok ? "已连接" : "未连接");
  }

  function setStageSize(w, h) {
    currentStageW = Math.max(1, parseInt(w, 10) || 1);
    currentStageH = Math.max(1, parseInt(h, 10) || 1);
    stage.style.width = currentStageW + "px";
    stage.style.height = currentStageH + "px";
    resW.value = String(currentStageW);
    resH.value = String(currentStageH);
    applyFit();
  }

  function applyFit() {
    if (!fitToggle.checked) {
      stage.style.transform = "";
      fitInfo.textContent = "";
      return;
    }
    var cw = stageContainer.clientWidth - 20;
    var ch = stageContainer.clientHeight - 20;
    var sx = cw / currentStageW;
    var sy = ch / currentStageH;
    var s = Math.max(0.05, Math.min(1.0, sx, sy));
    stage.style.transform = "scale(" + s.toFixed(4) + ")";
    fitInfo.textContent = "缩放=" + s.toFixed(3);
  }

  function ensureLayoutOptions(layouts) {
    var existing = {};
    for (var i = 0; i < layoutSelect.options.length; i++) existing[String(layoutSelect.options[i].value)] = 1;
    var incoming = {};
    for (var j = 0; j < (layouts || []).length; j++) {
      var item = layouts[j] || {};
      var idx = String(item.layout_index);
      incoming[idx] = 1;
      if (existing[idx]) continue;
      var opt = document.createElement("option");
      opt.value = idx;
      opt.textContent = idx + " - " + String(item.html_stem || item.html_file || "");
      layoutSelect.appendChild(opt);
    }
    var opts = [];
    for (var k = 0; k < layoutSelect.options.length; k++) opts.push(layoutSelect.options[k]);
    for (var m = 0; m < opts.length; m++) {
      var v = String(opts[m].value || "");
      if (v && !incoming[v]) opts[m].remove();
    }
  }

  function buildUiFrameUrl(layoutIndex) {
    var idx = parseInt(layoutIndex, 10) || 0;
    var url = "/ui.html?layout=" + encodeURIComponent(String(idx));
    if (flattenEnabled) url += "&flatten=1";
    return url;
  }

  function setLayout(layoutIndex) {
    var idx = parseInt(layoutIndex, 10) || 0;
    currentLayoutIndex = idx;
    var want = buildUiFrameUrl(idx);
    var cur = uiFrame.getAttribute("src") || "";
    if (cur !== want) uiFrame.setAttribute("src", want);
  }
  window.__localSimSetLayout = setLayout;

  function reloadUiFrame() {
    var base = buildUiFrameUrl(currentLayoutIndex);
    var sep = base.indexOf("?") >= 0 ? "&" : "?";
    uiFrame.setAttribute("src", base + sep + "_ts=" + String(Date.now()));
  }

  function applyPatchesToUi(patches) {
    var w = uiFrame.contentWindow;
    if (w && typeof w.__local_sim_apply_patches === "function") {
      w.__local_sim_apply_patches(patches || []);
      return true;
    }
    return false;
  }

  async function refreshStatus() {
    var st = await getJson(endpoint("status", "/api/local_sim/status"));
    var g = st.graph || {};
    var ui = st.ui || {};

    setStatus(true, (g.graph_name || "节点图") + " · " + (ui.current_ui_html_file || ui.ui_html_file || ""));
    ensureLayoutOptions(ui.layouts || []);
    if (typeof ui.current_layout_index === "number") currentLayoutIndex = ui.current_layout_index;

    paused = !!((st.server || {}).paused);
    var pauseBtn = $("btnPauseToggle");
    if (pauseBtn) {
      pauseBtn.textContent = paused ? "继续" : "暂停";
      pauseBtn.classList.toggle("primary", !paused);
    }

    if (layoutSelect.value !== String(currentLayoutIndex)) layoutSelect.value = String(currentLayoutIndex);
    setLayout(currentLayoutIndex);

    var rows = [
      { key: "graph_name", label: "节点图名称", value: g.graph_name },
      { key: "graph_type", label: "节点图类型", value: g.graph_type },
      { key: "graph_code_file", label: "节点图代码文件", value: g.graph_code_file },
      { key: "active_package_id", label: "当前包ID", value: g.active_package_id },
      { key: "ui_html_file", label: "UI页面文件", value: ui.ui_html_file },
      { key: "current_layout_index", label: "当前布局索引", value: ui.current_layout_index },
      { key: "paused", label: "是否暂停", value: String(paused) },
      { key: "ui_lv_defaults_count", label: "UI默认变量数量", value: (st.sim_notes || {}).ui_lv_defaults_count },
      { key: "layout_index_fallbacks", label: "布局索引回退表", value: JSON.stringify((st.sim_notes || {}).layout_index_fallbacks || {}, null, 0) },
      { key: "schema_version", label: "schema_version", value: st.schema_version },
      { key: "protocol_version", label: "protocol_version", value: st.protocol_version },
    ];
    kvSession.innerHTML = "";
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var kEl = document.createElement("div");
      var vEl = document.createElement("div");

      var b = document.createElement("b");
      b.textContent = row.label;
      b.title = row.key;
      kEl.appendChild(b);

      var v = row.value;
      vEl.textContent = (v === undefined || v === null) ? "" : String(v);
      kvSession.appendChild(kEl);
      kvSession.appendChild(vEl);
    }
  }

  async function refreshLastAction() {
    var data = await getJson(endpoint("last_action", "/api/local_sim/last_action"));
    var last = (data && data.last_action) ? data.last_action : null;
    var reportBox = $("lastActionReportBox");
    var rawBox = $("lastActionRawBox");
    if (!reportBox || !rawBox) return;

    var actionKey = "";
    if (last && typeof last === "object") {
      actionKey = String(last.kind || "") + "@" + String(last.timestamp || "");
    }

    // Raw view always updates (cheap), report updates only when action changes (or when trace cache grows)
    rawBox.value = last ? jsonSafeStringify(last) : "";
    rawBox.scrollTop = 0;

    var shouldRerenderReport = (actionKey !== lastRenderedActionKey);
    // If same action, still rerender occasionally because trace snippet may arrive later
    if (!shouldRerenderReport && last && typeof last === "object") {
      var now = Date.now();
      // throttle: rerender at most once per second
      shouldRerenderReport = (!reportBox.__localSimLastRenderAt) || (now - reportBox.__localSimLastRenderAt > 1000);
      if (shouldRerenderReport) reportBox.__localSimLastRenderAt = now;
    }
    if (shouldRerenderReport) {
      lastRenderedActionKey = actionKey;
      reportBox.value = last ? buildActionReport(last) : "";
      reportBox.scrollTop = 0;
    }
  }

  async function runValidate() {
    var resp = await postJson(endpoint("validate", "/api/local_sim/validate"), {});
    var box = $("validateBox");
    if (!box) return;
    box.value = jsonSafeStringify(resp);
    box.scrollTop = 0;
  }

  async function exportRepro() {
    var note = "exported_from_monitor";
    var resp = await postJson(endpoint("export_repro", "/api/local_sim/export_repro"), {
      include_entities: false,
      include_snapshot: true,
      include_trace: true,
      include_validation: true,
      include_last_action: true,
      recorded_actions: recordedActions || [],
      note: note,
    });
    var box = $("recordBox");
    if (box) {
      box.value = jsonSafeStringify({ export_response: resp, recorded: { version: 1, actions: recordedActions } });
      box.scrollTop = 0;
    }
    if (resp && resp.ok && resp.download_url) window.open(String(resp.download_url), "_blank");
  }

  function setRecordingEnabled(v) {
    recordingEnabled = !!v;
    var badge = $("recordBadge");
    if (!badge) return;
    badge.textContent = recordingEnabled ? "录制中" : "未录制";
    badge.style.color = recordingEnabled ? "rgba(90,162,255,.95)" : "rgba(255,255,255,.55)";
  }

  function appendRecordedAction(action) {
    recordedActions.push(action);
    var box = $("recordBox");
    if (!box) return;
    box.value = jsonSafeStringify({ version: 1, actions: recordedActions });
    box.scrollTop = box.scrollHeight;
  }

  function formatTraceKind(kindRaw) {
    var k = String(kindRaw || "").trim();
    if (!k) return "事件";
    var map = {
      ui_click: "UI点击",
      emit_signal: "发送信号",
      switch_layout: "切换布局",
      timer_fire: "定时器触发",
      event: "事件",
    };
    if (map[k]) return map[k] + " (" + k + ")";
    return k;
  }

  async function pollTrace() {
    var url = endpoint("trace", "/api/local_sim/trace") + "?since=" + encodeURIComponent(String(traceCursor));
    var data = await getJson(url);
    if (data && data.ok) {
      var evs = data.events || [];
      traceCursor = data.next || traceCursor;
      if (evs.length) {
        cacheTraceEvents(evs);
        for (var i = 0; i < evs.length; i++) {
          var e = evs[i] || {};
          var ts = e.timestamp ? ("[" + e.timestamp + "] ") : "";
          var kindRaw = (e.kind || "event");
          var kind = formatTraceKind(kindRaw);
          var msg = e.message ? (": " + e.message) : "";
          var details = e.details ? (" " + shortJson(e.details, 380)) : "";
          var line = ts + kind + msg + details;
          traceBox.value += line + "\n";
          if (recordingEnabled && (kindRaw === "ui_click" || kindRaw === "emit_signal")) {
            appendRecordedAction({ kind: kindRaw, details: e.details || {}, timestamp: e.timestamp || 0 });
          }
        }
        traceBox.scrollTop = traceBox.scrollHeight;
      }
    }
  }

  async function refreshEntities() {
    var data = await getJson(endpoint("entities", "/api/local_sim/entities"));
    entitiesBox.value = jsonSafeStringify(data);
    entitiesBox.scrollTop = 0;
  }

  async function clearTrace() {
    traceCursor = 0;
    traceBox.value = "";
    traceEventsCache = [];
    await postJson(endpoint("clear_trace", "/api/local_sim/clear_trace"), {});
  }

  async function togglePause() {
    var want = !paused;
    await postJson(endpoint("pause", "/api/local_sim/pause"), { paused: want });
    await refreshStatus();
  }

  async function stepOnce() {
    if (!paused) {
      alert("请先暂停，然后再单步执行");
      return;
    }
    var resp = await postJson(endpoint("step", "/api/local_sim/step"), { dt: 0.1 });
    if (resp && resp.ok) {
      var patches = resp.patches || [];
      applyPatchesToUi(patches);
    }
    await refreshStatus();
  }

  async function restartAll() {
    await postJson(endpoint("restart", "/api/local_sim/restart"), {});
    window.location.reload();
  }

  async function sendSignal() {
    var signal_id = String(($("signalId").value || "")).trim();
    if (!signal_id) {
      alert("请输入信号ID（signal_id）");
      return;
    }
    var params = {};
    var raw = String(($("signalParams").value || "")).trim();
    if (raw) params = JSON.parse(raw);
    var resp = await postJson(endpoint("emit_signal", "/api/local_sim/emit_signal"), { signal_id: signal_id, params: params });
    if (resp && resp.ok) {
      var patches = resp.patches || [];
      applyPatchesToUi(patches);
    }
  }

  function applyLayoutFromSelect() {
    var idx = parseInt(layoutSelect.value, 10) || 0;
    setLayout(idx);
  }

  function applyResFromInputs() {
    setStageSize(resW.value, resH.value);
  }

  function applyResFromPreset() {
    var v = String(resPreset.value || "");
    var m = v.match(/^(\d+)x(\d+)$/);
    if (!m) return;
    setStageSize(parseInt(m[1], 10), parseInt(m[2], 10));
  }

  function setActiveSizeButton(w, h) {
    var buttons = document.querySelectorAll('#sizeButtons button[data-res]');
    var key = String(w) + "x" + String(h);
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      var k = String(b.getAttribute("data-res") || "");
      if (k === key) b.classList.add("active");
      else b.classList.remove("active");
    }
  }

  function bindSizeButtons() {
    var buttons = document.querySelectorAll('#sizeButtons button[data-res]');
    for (var i = 0; i < buttons.length; i++) {
      (function (b) {
        b.addEventListener("click", function () {
          var k = String(b.getAttribute("data-res") || "");
          var m = k.match(/^(\d+)x(\d+)$/);
          if (!m) return;
          setStageSize(parseInt(m[1], 10), parseInt(m[2], 10));
          setActiveSizeButton(parseInt(m[1], 10), parseInt(m[2], 10));
        });
      })(buttons[i]);
    }
  }

  async function loadProtocolIfAny() {
    try {
      var p = await getJson(endpoint("protocol", "/api/local_sim/protocol"));
      if (p && p.endpoints) window.__LOCAL_SIM_PROTOCOL__ = p;
    } catch (e) {
      // protocol 加载失败：不阻塞页面，但 status 会在后续请求中暴露问题
      console.warn(e);
    }
  }

  // init
  flattenEnabled = (function () {
    var byQuery = getQueryParam("flatten") || getQueryParam("flat");
    if (byQuery) return isTruthyParam(byQuery);
    var v = window.localStorage ? window.localStorage.getItem("ayaya_local_sim_flatten_enabled") : "";
    if (v !== null && v !== undefined && String(v) !== "") return isTruthyParam(v);
    return true;
  })();
  flattenToggle.checked = !!flattenEnabled;

  $("btnApplyLayout").addEventListener("click", applyLayoutFromSelect);
  $("btnSendSignal").addEventListener("click", function () { sendSignal(); });
  $("btnReloadUi").addEventListener("click", function () { reloadUiFrame(); });
  $("btnRestartAll").addEventListener("click", function () { restartAll(); });
  $("btnPauseToggle").addEventListener("click", function () { togglePause(); });
  $("btnStep").addEventListener("click", function () { stepOnce(); });
  $("btnClearTrace").addEventListener("click", function () { clearTrace(); });
  $("btnRefreshEntities").addEventListener("click", function () { refreshEntities(); });
  $("btnUiContractCheck").addEventListener("click", function () { runUiContractCheck(); });

  $("btnRefreshLastAction").addEventListener("click", function () { refreshLastAction(); });
  $("btnToggleLastActionRaw").addEventListener("click", function () { setLastActionViewMode(!showLastActionRaw); });
  $("btnValidate").addEventListener("click", function () { runValidate(); });
  $("btnRecordToggle").addEventListener("click", function () { setRecordingEnabled(!recordingEnabled); });
  $("btnRecordClear").addEventListener("click", function () {
    recordedActions = [];
    appendRecordedAction({ kind: "reset", details: {}, timestamp: Date.now() / 1000.0 });
  });
  $("btnExportRepro").addEventListener("click", function () { exportRepro(); });
  $("btnAssertionsTemplate").addEventListener("click", function () { setAssertionsSpecToBox(assertionsTemplate()); });
  $("btnAssertionsFromLast").addEventListener("click", function () { fillAssertionsFromLastAction(); });
  $("btnRunAssertions").addEventListener("click", function () { runAssertionsAgainstLast(); });
  $("btnGenPytest").addEventListener("click", function () { generatePytestFromRecording(); });
  $("btnWatchTemplate").addEventListener("click", function () { setWatchSpecToBox(watchTemplate()); });
  $("btnApplyWatch").addEventListener("click", function () { applyWatchSpec(); });
  $("btnClearWatch").addEventListener("click", function () { clearWatchAll(); });

  $("btnApplyRes").addEventListener("click", applyResFromInputs);
  resPreset.addEventListener("change", applyResFromPreset);
  flattenToggle.addEventListener("change", function () {
    flattenEnabled = !!flattenToggle.checked;
    if (window.localStorage) window.localStorage.setItem("ayaya_local_sim_flatten_enabled", flattenEnabled ? "1" : "0");
    setLayout(currentLayoutIndex);
  });
  fitToggle.addEventListener("change", applyFit);
  window.addEventListener("resize", applyFit);

  bindSizeButtons();
  setStageSize(1600, 900);
  setActiveSizeButton(1600, 900);
  loadLastActionViewMode();

  loadProtocolIfAny().then(function () {
    refreshStatus();
    refreshEntities();
    refreshLastAction();
    setInterval(function () { refreshStatus(); }, 1500);
    setInterval(function () { pollTrace(); refreshLastAction(); }, 600);
  });
})();
