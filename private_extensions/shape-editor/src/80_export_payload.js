function getExportPosition(obj) {
    const point = obj.getPointByOrigin('left', 'top');
    return { left: point.x, top: point.y };
}

function buildExportObject(obj, groupInfo = null) {
    const pos = getExportPosition(obj);
    const fill = normalizeColor(obj.fill);
    const isBottomCenterPivot = BOTTOM_CENTER_PIVOT_COLORS.has(fill);
    const pivot = isBottomCenterPivot ? "bottom_center" : "center";
    const src = obj && obj.type === 'image' ? getReferenceImageSrcForPayload(obj) : '';

    const centerPx = obj.getPointByOrigin('center', 'center');
    const centerCentered = _pxPointToCentered(centerPx);

    // pivot 语义的锚点：用于导出到游戏 Transform.pos（缩放不会“挪动坐标”，因为坐标就是 pivot 点）
    // - center：锚点=几何中心
    // - bottom_center：锚点=底边中心（随旋转一起旋转）
    const anchorPx = isBottomCenterPivot ? obj.getPointByOrigin('center', 'bottom') : centerPx;
    const anchorCentered = _pxPointToCentered(anchorPx);
    return {
        type: obj.type,
        label: obj.label,
        color: fill,
        // reference image (not exported to gia; persisted for editor restore only)
        src: src,
        // legacy（像素系，左上原点），保留用于旧后端/旧调试
        left: Math.round(pos.left),
        top: Math.round(pos.top),
        width: Math.round(obj.getScaledWidth()),
        height: Math.round(obj.getScaledHeight()),
        angle: Math.round(obj.angle),
        // legacy（像素系锚点）：保存 pivot 点（便于后端 fallback & 调试）
        anchor: { x: Math.round(anchorPx.x), y: Math.round(anchorPx.y) },
        // 新口径（中心为原点，Y 向上）
        centered: { x: centerCentered.x, y: centerCentered.y },
        // 导出锚点（pivot 点）
        anchor_centered: { x: anchorCentered.x, y: anchorCentered.y },
        pivot: pivot,
        opacity: obj.opacity,
        isReference: obj.isReference || false,
        isLocked: obj.isLocked || false,
        group: groupInfo
    };
}

function collectExportObjects(objects, groupInfo = null) {
    const result = [];
    objects.forEach(obj => {
        if (obj.type === 'group' && obj.getObjects) {
            const info = {
                id: obj.id || null,
                label: obj.label || '组合'
            };
            const children = obj.getObjects();
            result.push(...collectExportObjects(children, info));
        } else {
            result.push(buildExportObject(obj, groupInfo));
        }
    });
    return result;
}

function exportJSON() {
    const objects = canvas.getObjects();
    const exportData = {
        meta: {
            timestamp: new Date().toISOString(),
            tool: 'qx-shape-editor',
            mode: 'full'
        },
        objects: collectExportObjects(objects)
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `shape_data_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function buildGiaExportPayload() {
    return {
        meta: {
            timestamp: new Date().toISOString(),
            tool: 'qx-shape-editor',
            mode: 'gia_decorations_group',
            target_rel_path: String(_selectedPlacementRelPath || '').trim(),
            coord_origin: 'center',
            coord_y_axis: 'up'
        },
        canvas: {
            width: canvas.getWidth(),
            height: canvas.getHeight()
        },
        objects: collectExportObjects(canvas.getObjects())
    };
}

