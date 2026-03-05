(function () {
  var g = (typeof window !== "undefined") ? window : this;
  if (!g.__LOCAL_SIM__) g.__LOCAL_SIM__ = {};
  var ns = g.__LOCAL_SIM__;

  function _trim(text) {
    return String(text || "").replace(/^\s+|\s+$/g, "");
  }

  function getQueryParam(name) {
    var key = String(name || "");
    if (!key) return "";
    try {
      if (typeof URLSearchParams === "function") {
        var sp = new URLSearchParams(String((g.location && g.location.search) ? g.location.search : ""));
        return String(sp.get(key) || "");
      }
    } catch (_e) {
      // ignore
    }
    var s = String((g.location && g.location.search) ? g.location.search : "");
    var m = s.match(new RegExp("[?&]" + key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^&]+)"));
    if (!m) return "";
    return String(m[1] || "");
  }

  function isTruthyParam(raw) {
    var t = _trim(raw).toLowerCase();
    return t === "1" || t === "true" || t === "yes" || t === "on";
  }

  // 静态资源路由（monitor/local_sim 注入脚本会用到）
  ns.WEB = ns.WEB || {
    monitor: "/",
    ui_html: "/ui.html",
    local_sim_js: "/local_sim.js",
    local_sim_shared_js: "/local_sim_shared.js",
    local_sim_flatten_overlay_mjs: "/local_sim_flatten_overlay.mjs",
    monitor_js: "/monitor.js",
  };

  function _defaultProtocol() {
    // 注意：这里只提供兜底，避免 monitor 在 protocol 注入/拉取失败时彻底不可用。
    // 真正的单一真源来自后端：GET /api/local_sim/protocol
    var base = "/api/local_sim";
    return {
      ok: true,
      protocol_version: 1,
      schema_version: 1,
      api_base: base,
      endpoints: {
        status: base + "/status",
        protocol: base + "/protocol",
        entities: base + "/entities",
        trace: base + "/trace",
        last_action: base + "/last_action",
        snapshot: base + "/snapshot",
        validation_status: base + "/validation_status",
        bootstrap: base + "/bootstrap",
        sync: base + "/sync",
        poll: base + "/poll",
        click: base + "/click",
        emit_signal: base + "/emit_signal",
        resolve_ui_key: base + "/resolve_ui_key",
        validate: base + "/validate",
        restart: base + "/restart",
        clear_trace: base + "/clear_trace",
        export_repro: base + "/export_repro",
        pause: base + "/pause",
        pause_status: base + "/pause_status",
        step: base + "/step",
      },
    };
  }

  function getProtocol() {
    var p = g.__LOCAL_SIM_PROTOCOL__;
    if (p && typeof p === "object" && p.endpoints && typeof p.endpoints === "object") {
      return p;
    }
    return _defaultProtocol();
  }

  function endpoint(name, fallback) {
    var key = _trim(name);
    if (!key) return String(fallback || "");
    var p = getProtocol();
    var ep = (p && p.endpoints && p.endpoints.hasOwnProperty && p.endpoints.hasOwnProperty(key)) ? p.endpoints[key] : "";
    if (ep) return String(ep);
    return String(fallback || "");
  }

  ns.trim = _trim;
  ns.getQueryParam = getQueryParam;
  ns.isTruthyParam = isTruthyParam;
  ns.getProtocol = getProtocol;
  ns.endpoint = endpoint;
})();

