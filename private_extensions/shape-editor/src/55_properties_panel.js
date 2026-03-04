// 更新属性面板UI
function updatePropPanel() {
    activeObject = canvas.getActiveObject();
    if (activeObject) {
        document.getElementById('prop-container').classList.remove('hidden');
        document.getElementById('no-selection').classList.add('hidden');
        updatePropInputs();
        if (activeObject.type === 'image') {
            document.getElementById('ref-opacity').value = activeObject.opacity;
        }
        const locked = activeObject.isLocked === true;
        const inputs = ['prop-x', 'prop-y', 'prop-w', 'prop-h', 'prop-angle', 'prop-scale'];
        inputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.disabled = locked;
        });
    } else {
        document.getElementById('prop-container').classList.add('hidden');
        document.getElementById('no-selection').classList.remove('hidden');
    }
}

function updatePropInputs() {
    if (!activeObject) return;
    // 画布编辑语义：一律按“几何中心点”显示/编辑位置，避免不同模板 pivot 影响画布对齐。
    // 游戏侧 pivot 不一致的问题在导出阶段（后端）统一转换。
    const center = activeObject.getPointByOrigin('center', 'center');
    const centered = _pxPointToCentered(center);
    document.getElementById('prop-x').value = centered.x;
    document.getElementById('prop-y').value = centered.y;
    document.getElementById('prop-w').value = Math.round(activeObject.getScaledWidth());
    document.getElementById('prop-h').value = Math.round(activeObject.getScaledHeight());
    document.getElementById('prop-angle').value = Math.round(activeObject.angle);
    document.getElementById('prop-scale').value = activeObject.scaleX.toFixed(2);
}

function applyProps() {
    if (!activeObject) return;
    if (activeObject.isLocked) return;
    
    const x = parseFloat(document.getElementById('prop-x').value);
    const y = parseFloat(document.getElementById('prop-y').value);
    const angle = parseFloat(document.getElementById('prop-angle').value);
    const scale = parseFloat(document.getElementById('prop-scale').value);

    const centerPx = _centeredToPxPoint({ x, y });
    activeObject.set({ angle: angle, scaleX: scale, scaleY: scale });
    // 按中心点定位（不让 pivot 影响画布对齐）
    activeObject.setPositionByOrigin(new fabric.Point(centerPx.x, centerPx.y), 'center', 'center');
    
    activeObject.setCoords();
    canvas.requestRenderAll();
    saveToLocal();
    saveHistory();
}

