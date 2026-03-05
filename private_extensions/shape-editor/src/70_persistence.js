// 数据持久化
function saveToLocal(addToHistory = false) {
    if (isBatching()) return;
    const json = JSON.stringify(canvas.toJSON(['isReference', 'id', 'label', 'isLocked']));
    localStorage.setItem('qx_shape_editor_data', json);
    if (addToHistory) saveHistory();
}

function loadFromLocal() {
    const json = localStorage.getItem('qx_shape_editor_data');
    if (json) {
        canvas.loadFromJSON(json, () => {
            canvas.renderAll();
            applyLockStates();
        });
    }
}

