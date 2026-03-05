import { rectFromWidget, rectArea, rectCenter, rectContainsPoint, rectIntersectionArea } from "./rect_utils.js";

function startsWithAny(text, prefixList) {
    var s = String(text || "");
    for (var i = 0; i < prefixList.length; i++) {
        var p = String(prefixList[i] || "");
        if (!p) {
            continue;
        }
        if (s.indexOf(p) === 0) {
            return true;
        }
    }
    return false;
}

export function pickAnchorLabel(anchorWidget) {
    if (!anchorWidget) {
        return "";
    }
    var label = String(anchorWidget._html_data_debug_label || "");
    if (label) {
        return label;
    }
    label = String(anchorWidget._html_button_aria_label || "");
    if (label) {
        return label;
    }
    var nameText = String(anchorWidget.widget_name || "");
    nameText = nameText.replace(/^按钮_道具展示_/, "");
    return nameText;
}

export function collectButtonAnchors(allWidgets) {
    var anchors = [];
    for (var wi = 0; wi < allWidgets.length; wi++) {
        var wItem = allWidgets[wi];
        if (!wItem) {
            continue;
        }
        if (String(wItem.widget_type || "") !== "道具展示") {
            continue;
        }
        if (wItem.is_builtin) {
            continue;
        }
        var isInteractiveAnchor = wItem.settings && wItem.settings.can_interact === true;
        var isButtonAnchor = String(wItem.widget_name || "").indexOf("按钮_道具展示_") === 0;
        if (!isInteractiveAnchor || !isButtonAnchor) {
            continue;
        }
        anchors.push(wItem);
    }
    return anchors;
}

export function groupWidgetsByAnchors(allWidgets, anchors) {
    var groupedWidgetIds = new Set();
    var membersByAnchorId = {};
    var anchorRectCache = {};
    var anchorAreaCache = {};
    for (var ai = 0; ai < anchors.length; ai++) {
        var anchor = anchors[ai];
        membersByAnchorId[String(anchor.widget_id || "")] = [anchor];
        groupedWidgetIds.add(String(anchor.widget_id || ""));
        var aRect = rectFromWidget(anchor);
        anchorRectCache[String(anchor.widget_id || "")] = aRect;
        anchorAreaCache[String(anchor.widget_id || "")] = rectArea(aRect);
    }

    // 说明：
    // - “高亮底板_”是“选中高亮底板”矩形（约定：ui_key base 以 `_highlight` 结尾）；
    //   需要把它吸附到按钮模板里，否则会变成单独模板，达不到“减少控件组”的目的。
    var progressPrefixes = ["按钮_", "阴影_", "边框_", "高亮底板_"];
    var textPrefix = "文本_";
    var iconPrefix = "图标_";

    for (var wi2 = 0; wi2 < allWidgets.length; wi2++) {
        var widget = allWidgets[wi2];
        if (!widget) {
            continue;
        }
        var widgetId = String(widget.widget_id || "");
        if (groupedWidgetIds.has(widgetId)) {
            continue;
        }
        if (widget.is_builtin) {
            continue;
        }

        var widgetType = String(widget.widget_type || "");
        var widgetName = String(widget.widget_name || "");
        if (widgetType !== "进度条" && widgetType !== "文本框" && widgetType !== "道具展示") {
            continue;
        }
        if (widgetType === "进度条") {
            if (!startsWithAny(widgetName, progressPrefixes)) {
                continue;
            }
        } else if (widgetType === "文本框") {
            if (widgetName.indexOf(textPrefix) !== 0) {
                continue;
            }
        } else {
            // icon 道具展示：只能是“不可交互”的单 ICON 转换产物
            if (!(widget.settings && widget.settings.can_interact === false)) {
                continue;
            }
            if (widgetName.indexOf(iconPrefix) !== 0) {
                continue;
            }
        }

        var wRect2 = rectFromWidget(widget);
        if (rectArea(wRect2) <= 0) {
            continue;
        }

        var bestAnchor = null;
        var bestArea = 0;
        for (var aj = 0; aj < anchors.length; aj++) {
            var anchor2 = anchors[aj];
            var aId = String(anchor2.widget_id || "");
            var aRect2 = anchorRectCache[aId];
            var area2 = rectIntersectionArea(wRect2, aRect2);
            if (area2 > bestArea) {
                bestArea = area2;
                bestAnchor = anchor2;
            }
        }
        if (!bestAnchor || bestArea <= 0) {
            continue;
        }

        var bestAnchorId = String(bestAnchor.widget_id || "");
        var bestAnchorRect = anchorRectCache[bestAnchorId];
        var wCenter = rectCenter(wRect2);
        var aCenter = rectCenter(bestAnchorRect);

        if (widgetType === "文本框" || widgetType === "道具展示") {
            if (!rectContainsPoint(bestAnchorRect, wCenter.x, wCenter.y)) {
                continue;
            }
        } else {
            if (!(rectContainsPoint(bestAnchorRect, wCenter.x, wCenter.y) || rectContainsPoint(wRect2, aCenter.x, aCenter.y))) {
                continue;
            }
            var buttonArea = Number(anchorAreaCache[bestAnchorId] || 0);
            if (buttonArea > 0) {
                if (rectArea(wRect2) > buttonArea * 6.0) {
                    continue;
                }
            }
        }

        membersByAnchorId[bestAnchorId].push(widget);
        groupedWidgetIds.add(widgetId);
    }

    return {
        groupedWidgetIds: groupedWidgetIds,
        membersByAnchorId: membersByAnchorId
    };
}

