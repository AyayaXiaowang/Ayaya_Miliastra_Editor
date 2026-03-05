export function resolvePreviewElementLabel(targetElement) {
    if (!targetElement) {
        return "";
    }
    var dbg = targetElement.getAttribute ? String(targetElement.getAttribute("data-debug-label") || "").trim() : "";
    if (dbg) {
        return dbg;
    }
    var id = targetElement.id ? String(targetElement.id || "").trim() : "";
    if (id) {
        return "#" + id;
    }
    var className = targetElement.className ? String(targetElement.className || "").trim() : "";
    if (className) {
        var tokens = className.split(/\s+/).filter(function (x) { return !!x; }).slice(0, 3);
        if (tokens.length > 0) {
            return "." + tokens.join(".");
        }
    }
    return String(targetElement.tagName || "").toLowerCase();
}

