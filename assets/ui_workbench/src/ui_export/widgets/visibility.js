function _normalizeLower(text) {
    return String(text || "").trim().toLowerCase();
}

export function inferInitialVisibleFromSource(source, fallbackValue) {
    var fallback = fallbackValue === undefined ? true : !!fallbackValue;
    if (!source) {
        return fallback;
    }
    var hints = source.styleHints || null;
    if (!hints) {
        return fallback;
    }
    var displayText = _normalizeLower(hints.display);
    if (displayText === "none") {
        return false;
    }
    var visibilityText = _normalizeLower(hints.visibility);
    if (visibilityText && visibilityText !== "visible") {
        return false;
    }
    // NOTE:
    // - 多状态控件的非默认态常用 `opacity:0 + pointer-events:none` 做“初始隐藏”；
    // - 这里没有 pointer-events 信息，但为了让导出端 `initial_visible` 更符合“视觉初始态”，仍将 opacity≈0 视为不可见。
    var opacityText = _normalizeLower(hints.opacity);
    if (opacityText) {
        var op = Number.parseFloat(opacityText);
        if (isFinite(op) && op <= 0.001) {
            return false;
        }
    }
    return fallback;
}

