function _normalizeUiStateAttr(text) {
    return String(text || "").trim();
}

function _parseUiStateBool(text) {
    var lowered = String(text || "").trim().toLowerCase();
    if (!lowered) {
        return false;
    }
    return lowered === "1" || lowered === "true" || lowered === "yes" || lowered === "on";
}

export function getUiStateMetaFromSource(source) {
    if (!source || !source.attributes) {
        return null;
    }
    var group = _normalizeUiStateAttr(source.attributes.dataUiStateGroup);
    if (!group) {
        return null;
    }
    var state = _normalizeUiStateAttr(source.attributes.dataUiState);
    var isDefault = _parseUiStateBool(source.attributes.dataUiStateDefault);
    return { group: group, state: state, isDefault: isDefault };
}

export function applyUiStateMetaToPayload(payload, source) {
    if (!payload) {
        return payload;
    }
    var meta = getUiStateMetaFromSource(source);
    if (!meta) {
        return payload;
    }
    payload.__ui_state_group = meta.group;
    payload.__ui_state = meta.state;
    payload.__ui_state_default = meta.isDefault;
    // 多状态控件的初始可见性：默认态可见，非默认态不可见。
    // 这是“写入 GIL 时也能正确初始显隐”的基础设施（不能只依赖 HTML 的 visibility:hidden）。
    payload.initial_visible = !!meta.isDefault;
    return payload;
}

export function inferUiStateMetaFromWidgetList(widgetList) {
    if (!widgetList || widgetList.length <= 0) {
        return null;
    }
    var first = widgetList[0] || null;
    if (!first || !first.__ui_state_group) {
        return null;
    }
    var group = String(first.__ui_state_group || "").trim();
    if (!group) {
        return null;
    }
    var state = String(first.__ui_state || "").trim();
    var isDefault = !!first.__ui_state_default;
    for (var i = 1; i < widgetList.length; i++) {
        var w = widgetList[i] || {};
        if (String(w.__ui_state_group || "").trim() !== group) {
            return null;
        }
        if (String(w.__ui_state || "").trim() !== state) {
            return null;
        }
        if (!!w.__ui_state_default !== isDefault) {
            return null;
        }
    }
    return { group: group, state: state, isDefault: isDefault };
}

