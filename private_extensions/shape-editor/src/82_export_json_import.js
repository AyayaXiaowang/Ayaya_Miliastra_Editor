function exportSelectedGroupJSON() {
    const active = canvas.getActiveObject();
    if (!active || active.type !== 'group') {
        toastToUi('warn', '请先选中一个组');
        logToUi('WARN', '导出选中组：未选中 group');
        return;
    }
    const groupInfo = { id: active.id || null, label: active.label || '组合' };
    const exportData = {
        meta: {
            timestamp: new Date().toISOString(),
            tool: 'qx-shape-editor',
            mode: 'group'
        },
        group: groupInfo,
        objects: collectExportObjects(active.getObjects(), groupInfo)
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `shape_group_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function importJSON(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(f) {
        const json = JSON.parse(f.target.result);
        if (json.objects && json.meta) {
            toastToUi('warn', '提示：简化JSON可能无法完全还原编辑状态。建议优先使用本地存储或 Fabric 原生导出。', 3200);
            logToUi('WARN', '导入：检测到简化JSON，可能无法完全还原编辑状态。');
        }
        canvas.loadFromJSON(json, () => {
            canvas.renderAll();
            applyLockStates();
            saveToLocal();
            saveHistory();
            toastToUi('info', '已导入');
            logToUi('INFO', '已导入 JSON');
        });
    };
    reader.readAsText(file);
    e.target.value = '';
}

