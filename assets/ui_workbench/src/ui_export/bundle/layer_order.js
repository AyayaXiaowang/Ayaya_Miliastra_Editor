export function minLayerIndex(widgetList) {
    var minLayer = null;
    for (var i = 0; i < widgetList.length; i++) {
        var layer = Number(widgetList[i] && widgetList[i].layer_index !== undefined ? widgetList[i].layer_index : 0);
        if (!isFinite(layer)) {
            layer = 0;
        }
        if (minLayer === null || layer < minLayer) {
            minLayer = layer;
        }
    }
    return minLayer === null ? 0 : minLayer;
}

