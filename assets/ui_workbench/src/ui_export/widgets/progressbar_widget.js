import { buildStableHtmlComponentKey, buildStableUiKey } from "../keys.js";
import { applyUiStateMetaToPayload } from "../ui_state.js";
import { detectProgressBarShapeForRect, mapToNearestProgressBarColor } from "../color_font.js";
import { inferInitialVisibleFromSource } from "./visibility.js";

export function buildProgressBarWidget(widgetId, widgetName, rect, zIndex, colorText, progressPercent, warningList, source, uiKeyKind, overrides) {
    var mapped = mapToNearestProgressBarColor(colorText, warningList, widgetName);
    var overrideSettings = (overrides && overrides.settings) ? overrides.settings : (overrides || null);
    var initialVisible = overrideSettings && overrideSettings.initial_visible !== undefined ? !!overrideSettings.initial_visible : inferInitialVisibleFromSource(source, true);
    // NOTE:
    // - 进度条的 current/min/max 在实际存档中需要绑定到“自定义变量”才能稳定工作；
    // - 这里默认导出为一套“共享装饰进度条变量”（关卡变量），由后端写回链路负责自动创建（若不存在）。
    var currentVar = "关卡.UI_装饰进度条_当前值";
    var minVar = "关卡.UI_装饰进度条_最小值";
    var maxVar = "关卡.UI_装饰进度条_最大值";

    // HTML 注解：允许对“真实进度条”指定变量绑定（避免所有矩形都绑定同一套装饰变量）。
    // 约定：
    // - 标注：data-ui-role="progressbar"
    // - 绑定：data-progress-current-var / data-progress-min-var / data-progress-max-var
    function _normalizeBindingText(raw) {
        var text = String(raw || "").trim();
        if (!text) {
            return "";
        }
        // 允许用户误用 moustache 包裹：{{ps.xxx}} -> ps.xxx
        var m = /^\{\{\s*([^{}]+?)\s*\}\}$/.exec(text);
        if (m && m[1]) {
            return String(m[1] || "").trim();
        }
        return text;
    }

    var attrs = (source && source.attributes) ? source.attributes : null;
    var uiRoleText = attrs && attrs.dataUiRole ? String(attrs.dataUiRole || "").trim() : "";
    var isProgressbarRole = uiRoleText && uiRoleText.toLowerCase() === "progressbar";

    var overrideCurrent = attrs ? _normalizeBindingText(attrs.dataProgressCurrentVar) : "";
    var overrideMin = attrs ? _normalizeBindingText(attrs.dataProgressMinVar) : "";
    var overrideMax = attrs ? _normalizeBindingText(attrs.dataProgressMaxVar) : "";
    var hasAnyOverride = !!(overrideCurrent || overrideMin || overrideMax);

    function _normalizeProgressShapeText(raw) {
        var text = String(raw || "").trim().toLowerCase();
        if (!text) {
            return "";
        }
        // 允许用户写中文/英文/缩写
        if (text === "横向" || text === "horizontal" || text === "h") {
            return "横向";
        }
        if (text === "纵向" || text === "vertical" || text === "v") {
            return "纵向";
        }
        if (text === "圆环" || text === "ring" || text === "circle") {
            return "圆环";
        }
        return "";
    }

    // shape 优先级：
    // 1) HTML 显式声明 data-progress-shape（横向/纵向/圆环）
    // 2) 真实进度条（显式 progressbar 语义或提供变量绑定）默认强制横向（不再依赖几何推断）
    // 3) 纯装饰矩形：按几何推断（用于“装饰进度条 / 条形底色”等）
    var explicitShape = attrs ? _normalizeProgressShapeText(attrs.dataProgressShape) : "";
    var isRealProgressbar = isProgressbarRole || hasAnyOverride;
    var shape = "横向";
    if (explicitShape) {
        shape = explicitShape;
    } else if (!isRealProgressbar) {
        shape = detectProgressBarShapeForRect(rect, source);
    }
    if (warningList && attrs && attrs.dataProgressShape && !explicitShape) {
        warningList.push("进度条 data-progress-shape 值不受支持（仅支持 横向/纵向/圆环 或 horizontal/vertical/ring）：[" + String(widgetName || "") + "] shape=" + String(attrs.dataProgressShape || ""));
    }

    if (isProgressbarRole || hasAnyOverride) {
        if (overrideCurrent) {
            currentVar = overrideCurrent;
        }
        if (overrideMin) {
            minVar = overrideMin;
        }
        if (overrideMax) {
            maxVar = overrideMax;
        }
        if (warningList) {
            if (isProgressbarRole && !hasAnyOverride) {
                warningList.push("进度条已标注 data-ui-role=\"progressbar\" 但未提供 data-progress-*-var 绑定；将回退为默认装饰进度条变量：[" + String(widgetName || "") + "]");
            } else {
                if (!overrideCurrent) {
                    warningList.push("进度条缺少 data-progress-current-var（当前值绑定）；将回退默认变量：[" + String(widgetName || "") + "]");
                }
                if (!overrideMin) {
                    warningList.push("进度条缺少 data-progress-min-var（最小值绑定）；将回退默认变量：[" + String(widgetName || "") + "]");
                }
                if (!overrideMax) {
                    warningList.push("进度条缺少 data-progress-max-var（最大值绑定）；将回退默认变量：[" + String(widgetName || "") + "]");
                }
            }
        }
    }

    // 进度条“填充百分比”语义：在不允许常量数值绑定的前提下，用变量组合表达：
    // - progressPercent <= 0：视作“空条”，令 current_var=min_var（这样只显示进度条底色，可用于黑色阴影）
    // - 其它：视作“满条”，令 current_var=当前值（默认 current=max）
    var percentNumber = Number(progressPercent);
    var currentBinding = currentVar;
    // 注意：真实进度条必须绑定 current_var，不应被“装饰用空条语义”覆盖。
    if (!isRealProgressbar && isFinite(percentNumber) && percentNumber <= 0) {
        currentBinding = minVar;
    }

    var attrsTemplate = (source && source.attributes) ? source.attributes : null;
    var dataUiSaveTemplate = attrsTemplate ? (attrsTemplate.dataUiSaveTemplate || attrsTemplate.componentOwnerDataUiSaveTemplate || null) : null;

    return applyUiStateMetaToPayload({
        ui_key: buildStableUiKey(source, uiKeyKind || "progressbar"),
        __html_component_key: buildStableHtmlComponentKey(source),
        __ui_custom_template_name: (dataUiSaveTemplate ? String(dataUiSaveTemplate || "").trim() : ""),
        widget_id: widgetId,
        widget_type: "进度条",
        widget_name: widgetName,
        position: [Number(rect.left || 0), Number(rect.top || 0)],
        size: [Number(rect.width || 0), Number(rect.height || 0)],
        initial_visible: initialVisible,
        layer_index: Number.isFinite(zIndex) ? Math.trunc(zIndex) : 0,
        is_builtin: false,
        settings: {
            shape: shape,
            style: "不显示",
            color: mapped.color,
            current_var: currentBinding,
            min_var: minVar,
            max_var: maxVar
        },
        _html_color_source: mapped.mappedFrom
    }, source);
}

