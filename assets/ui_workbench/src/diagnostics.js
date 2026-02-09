// Diagnostics (Issue model) for UI HTML Workbench.
//
// Design goals:
// - Structured: machine-readable issues with stable codes.
// - Human-friendly: consistent formatting for the "校验结果" panel.
// - AI-friendly: build a compact "AI 修复包" to close the loop quickly.
//
// NOTE: No try/catch by design. Fail-fast.

function _safeText(v) {
    return String(v === undefined || v === null ? "" : v);
}

function _safeTrim(v) {
    return _safeText(v).trim();
}

export function createIssue(payload) {
    var p = payload || {};
    var code = _safeTrim(p.code);
    var severity = _safeTrim(p.severity).toLowerCase();
    var message = _safeTrim(p.message);
    if (!code) {
        throw new Error("Issue.code 不能为空");
    }
    if (!message) {
        throw new Error("Issue.message 不能为空");
    }
    if (severity !== "error" && severity !== "warning" && severity !== "info") {
        throw new Error("Issue.severity 必须为 error/warning/info");
    }
    var issue = {
        code: code,
        severity: severity,
        message: message,
        target: p.target || null,
        evidence: p.evidence || null,
        fix: p.fix || null,
    };
    return issue;
}

function _issueDedupeKey(issue) {
    var it = issue || {};
    var code = _safeTrim(it.code);
    var severity = _safeTrim(it.severity);
    var msg = _safeTrim(it.message);
    var t = it.target || {};
    var id = _safeTrim(t.id);
    var uiKey = _safeTrim(t.ui_key);
    var elementIndex = t.element_index !== undefined && t.element_index !== null ? _safeTrim(t.element_index) : "";
    return [severity, code, id, uiKey, elementIndex, msg].join("|");
}

export function dedupeIssues(issues) {
    var list = Array.isArray(issues) ? issues : [];
    var seen = new Set();
    var out = [];
    for (var i = 0; i < list.length; i++) {
        var it = list[i];
        if (!it) continue;
        var k = _issueDedupeKey(it);
        if (seen.has(k)) continue;
        seen.add(k);
        out.push(it);
    }
    return out;
}

export function concatIssues() {
    var out = [];
    for (var i = 0; i < arguments.length; i++) {
        var list = arguments[i];
        if (!list) continue;
        if (!Array.isArray(list)) {
            throw new Error("concatIssues 只接受 Issue[]");
        }
        for (var j = 0; j < list.length; j++) {
            var it = list[j];
            if (!it) continue;
            out.push(it);
        }
    }
    return out;
}

export function summarizeIssues(issues) {
    var list = Array.isArray(issues) ? issues : [];
    var out = { error: 0, warning: 0, info: 0, total: 0 };
    for (var i = 0; i < list.length; i++) {
        var it = list[i];
        if (!it) continue;
        var s = _safeTrim(it.severity).toLowerCase();
        if (s === "error") out.error += 1;
        else if (s === "warning") out.warning += 1;
        else if (s === "info") out.info += 1;
        out.total += 1;
    }
    return out;
}

export function splitIssuesBySeverity(issues) {
    var list = Array.isArray(issues) ? issues : [];
    var errors = [];
    var warnings = [];
    var infos = [];
    for (var i = 0; i < list.length; i++) {
        var it = list[i];
        if (!it) continue;
        var s = _safeTrim(it.severity).toLowerCase();
        if (s === "error") errors.push(it);
        else if (s === "warning") warnings.push(it);
        else infos.push(it);
    }
    return { errors: errors, warnings: warnings, infos: infos };
}

export function createDiagnosticsCollector(opts) {
    var o = opts || {};
    var issues = [];
    var allowDuplicates = !!o.allow_duplicates;
    var seen = new Set();

    function _push(issue) {
        if (!issue) return;
        if (allowDuplicates) {
            issues.push(issue);
            return;
        }
        var k = _issueDedupeKey(issue);
        if (seen.has(k)) return;
        seen.add(k);
        issues.push(issue);
    }

    function warn(payload) {
        var p = payload || {};
        _push(createIssue({
            code: p.code,
            severity: "warning",
            message: p.message,
            target: p.target || null,
            evidence: p.evidence || null,
            fix: p.fix || null,
        }));
    }

    function info(payload) {
        var p = payload || {};
        _push(createIssue({
            code: p.code,
            severity: "info",
            message: p.message,
            target: p.target || null,
            evidence: p.evidence || null,
            fix: p.fix || null,
        }));
    }

    function error(payload) {
        var p = payload || {};
        _push(createIssue({
            code: p.code,
            severity: "error",
            message: p.message,
            target: p.target || null,
            evidence: p.evidence || null,
            fix: p.fix || null,
        }));
    }

    return {
        issues: issues,
        push: _push,
        warn: warn,
        info: info,
        error: error,
    };
}

function _formatTarget(target) {
    var t = target || null;
    if (!t) return "";
    var id = t.id ? _safeTrim(t.id) : "";
    var uiKey = t.ui_key ? _safeTrim(t.ui_key) : "";
    var selector = t.css_selector ? _safeTrim(t.css_selector) : "";
    var elementIndex = t.element_index !== undefined && t.element_index !== null ? _safeTrim(t.element_index) : "";
    var parts = [];
    if (uiKey) parts.push("ui_key=" + uiKey);
    if (id) parts.push("id=" + id);
    if (elementIndex) parts.push("idx=" + elementIndex);
    if (selector) parts.push("sel=" + selector);
    return parts.length > 0 ? (" (" + parts.join(", ") + ")") : "";
}

export function formatIssuesAsText(issues, opts) {
    var o = opts || {};
    var list = Array.isArray(issues) ? issues : [];
    var s = summarizeIssues(list);
    var lines = [];
    var title = _safeTrim(o.title) || "Diagnostics";
    lines.push("【" + title + "】 errors=" + s.error + " warnings=" + s.warning + " infos=" + s.info + " total=" + s.total);
    if (s.total <= 0) {
        lines.push("通过：未发现问题。");
        return lines.join("\n");
    }
    lines.push("");
    for (var i = 0; i < list.length; i++) {
        var it = list[i];
        if (!it) continue;
        var sev = _safeTrim(it.severity).toLowerCase();
        var sevTag = sev === "error" ? "E" : (sev === "warning" ? "W" : "I");
        var code = _safeTrim(it.code);
        var msg = _safeTrim(it.message);
        var tgt = _formatTarget(it.target);
        lines.push("[" + sevTag + "] " + code + "： " + msg + tgt);
        if (it.fix && it.fix.suggestion) {
            lines.push("     fix: " + _safeTrim(it.fix.suggestion));
        }
    }
    return lines.join("\n");
}

export function issuesToJsonText(issues) {
    var list = Array.isArray(issues) ? issues : [];
    return JSON.stringify(list, null, 2);
}

function _extractSnippetById(htmlText, idText, contextLineCount) {
    var html = _safeText(htmlText);
    var idv = _safeTrim(idText);
    if (!idv) return "";
    var lines = html.split(/\r?\n/);
    var needle = "id=\"" + idv + "\"";
    var idx = -1;
    for (var i = 0; i < lines.length; i++) {
        if (lines[i] && lines[i].indexOf(needle) >= 0) {
            idx = i;
            break;
        }
    }
    if (idx < 0) {
        // also try single quotes
        needle = "id='" + idv + "'";
        for (var j = 0; j < lines.length; j++) {
            if (lines[j] && lines[j].indexOf(needle) >= 0) {
                idx = j;
                break;
            }
        }
    }
    if (idx < 0) return "";
    var n = Number(contextLineCount || 10);
    if (!isFinite(n) || n < 3) n = 10;
    var start = Math.max(0, idx - n);
    var end = Math.min(lines.length, idx + n + 1);
    var chunk = lines.slice(start, end).join("\n");
    return chunk.trim();
}

export function buildAiFixPack(payload) {
    var p = payload || {};
    var htmlText = _safeText(p.html_text);
    var issues = Array.isArray(p.issues) ? p.issues : [];
    var summary = summarizeIssues(issues);
    var title = _safeTrim(p.title) || "UI HTML Workbench - AI 修复包";

    var headerLines = [];
    headerLines.push("【" + title + "】");
    headerLines.push("目标：把 errors 修到 0；warnings 可保留（但尽量减少）。");
    headerLines.push("");
    headerLines.push("硬约束：");
    headerLines.push("- 禁止 <script> / meta refresh");
    headerLines.push("- 页面不得出现滚动条（html/body overflow:hidden）");
    headerLines.push("- 不要删改已有的 data-ui-key / data-ui-state-* / data-ui-role 标注（保持语义锚点稳定）");
    headerLines.push("");
    headerLines.push("当前统计：errors=" + summary.error + " warnings=" + summary.warning + " infos=" + summary.info);
    headerLines.push("");
    headerLines.push("## Diagnostics JSON");
    headerLines.push(issuesToJsonText(issues));

    // Optional: include small, high-signal snippets for targeted fixes.
    var snippetLines = [];
    var seenIds = new Set();
    for (var i = 0; i < issues.length; i++) {
        var it = issues[i] || {};
        var idv = it && it.target && it.target.id ? _safeTrim(it.target.id) : "";
        if (!idv) continue;
        if (seenIds.has(idv)) continue;
        seenIds.add(idv);
        if (seenIds.size > 5) break;
        var snip = _extractSnippetById(htmlText, idv, 12);
        if (!snip) continue;
        snippetLines.push("");
        snippetLines.push("## Snippet: id=\"" + idv + "\"");
        snippetLines.push(snip);
    }

    // Always include full HTML at the end (AI can choose to ignore), but keep it as-is.
    // This is intentional: in practice, repairs may need surrounding context.
    var footerLines = [];
    footerLines.push("");
    footerLines.push("## HTML（待修复）");
    footerLines.push(htmlText);

    return headerLines.concat(snippetLines).concat(footerLines).join("\n");
}

