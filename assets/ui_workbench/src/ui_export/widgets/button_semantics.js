function _splitClassTokens(classNameText) {
    var raw = String(classNameText || "");
    if (!raw) {
        return [];
    }
    return raw.split(/\s+/).map(function (t) { return String(t || "").trim(); }).filter(function (t) { return !!t; });
}

function _hasExactClassToken(classNameText, token) {
    var needle = String(token || "").trim();
    if (!needle) {
        return false;
    }
    var tokens = _splitClassTokens(classNameText);
    for (var i = 0; i < tokens.length; i++) {
        if (tokens[i] === needle) {
            return true;
        }
    }
    return false;
}

export function isButtonLikeSource(source) {
    if (!source) {
        return false;
    }
    var tag = String(source.tagName || "").toLowerCase();
    // 强约束：仅允许“显式语义标注”为按钮（避免把纯样式/容器误判为可交互按钮）。
    // - role="button"：标准 ARIA 语义（用于 div/span 等）
    // - data-ui-role="button"：工具私有约定（更直观，推荐）
    // - data-ui-interact-key / data-ui-action：明确声明“可交互意图”的字段（视为显式按钮语义）
    //
    // 注意：`<button>` 标签本身 **不再** 自动视为“可交互按钮”。
    // 设计原因：UI mockup 中大量 `<button>` 只是为了便捷样式/排版，
    // 若自动判定会导致“同页可交互按钮数 > 14”并阻断导出。
    var attrs = source.attributes || null;
    if (attrs) {
        // 显式“非按钮”导出提示：允许作者保留 `<button data-ui-key="...">` 作为视觉/布局容器，
        // 但要求导出阶段不要把它当“按钮锚点”（避免生成“道具展示(可交互)”控件占用槽位）。
        //
        // 约定：data-ui-export-as="decor"（大小写不敏感）
        var exportAs = String(attrs.dataUiExportAs || attrs.componentOwnerDataUiExportAs || "").trim().toLowerCase();
        if (exportAs === "decor") {
            return false;
        }
        var uiRole = String(attrs.dataUiRole || "").trim().toLowerCase();
        if (uiRole === "button") {
            return true;
        }
        var ariaRole = String(attrs.role || "").trim().toLowerCase();
        if (ariaRole === "button") {
            return true;
        }
        var interactKey = String(attrs.dataUiInteractKey || "").trim();
        if (interactKey) {
            return true;
        }
        var uiAction = String(attrs.dataUiAction || "").trim();
        if (uiAction) {
            return true;
        }
        // 兜底：`<button data-ui-key="...">` 通常是用户明确意图的“可交互按钮锚点”。
        // 仅对真实 button + 显式 data-ui-key 启用（避免把纯样式 `<button>` 误判为按钮）。
        var uiKey = String(attrs.dataUiKey || "").trim();
        if (tag === "button" && uiKey) {
            return true;
        }
    }
    void tag; // 保留以便未来扩展（当前不依赖 tag 自动判定）
    return false;
}

