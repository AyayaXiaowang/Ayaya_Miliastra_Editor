async function exportGiaDecorationsGroup() {
    const payload = buildGiaExportPayload();
    const resp = await fetch('/api/shape_editor/export_gia', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json; charset=utf-8'
        },
        body: JSON.stringify(payload)
    });
    const text = await resp.text();
    if (!resp.ok) {
        logToUi('ERROR', `导出失败（HTTP ${resp.status}）`);
        logToUi('ERROR', text);
        toastToUi('error', `导出失败（HTTP ${resp.status}）`, 2600);
        return;
    }
    const obj = JSON.parse(text);
    _applyPersistedReferenceImagesFromResponse(obj);
    logToUi('INFO', `导出完成：decorations=${obj.decorations_count}`);
    logToUi('INFO', `output_gia_file: ${obj.output_gia_file}`);
    logToUi('INFO', `exported_to: ${obj.exported_to}`);
    toastToUi('info', `导出完成：${obj.decorations_count} 个装饰物`);
}

function exportGiaAsEntity() {
    logToUi('INFO', '开始导出：实体');
    return Promise.resolve()
        .then(() => {
            const payload = buildGiaExportPayload();
            const count = Array.isArray(payload.objects) ? payload.objects.length : 0;
            logToUi('INFO', `导出：实体 payload 已构建 objects=${count}`);
            const body = JSON.stringify(payload);
            logToUi('INFO', `导出：实体 请求发送 bytes=${body.length}`);
            return fetch('/api/shape_editor/export_gia_entity', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json; charset=utf-8' },
                body
            });
        })
        .then(resp => resp.text().then(text => ({ resp, text })))
        .then(({ resp, text }) => {
            logToUi('INFO', `导出：实体 响应已收到 status=${resp.status}`);
            if (!resp.ok) {
                logToUi('ERROR', `导出为实体失败（HTTP ${resp.status}）`);
                logToUi('ERROR', text);
                toastToUi('error', `导出为实体失败（HTTP ${resp.status}）`, 2600);
                return;
            }
            const obj = JSON.parse(text);
            _applyPersistedReferenceImagesFromResponse(obj);
            logToUi('INFO', `导出为实体完成：decorations=${obj.decorations_count}`);
            logToUi('INFO', `output_gia_file: ${obj.output_gia_file}`);
            logToUi('INFO', `exported_to: ${obj.exported_to}`);
            toastToUi('info', `导出为实体完成：${obj.decorations_count} 个装饰物`);
        })
        .catch(err => {
            const msg = (err && err.message) ? err.message : String(err);
            logToUi('ERROR', `导出为实体异常（可能是后端崩溃/断开连接）：${msg}`);
            toastToUi('error', '导出为实体异常（请看日志）', 2600);
            throw err;
        });
}

function exportGiaAsTemplate() {
    logToUi('INFO', '开始导出：元件');
    return Promise.resolve()
        .then(() => {
            const payload = buildGiaExportPayload();
            const count = Array.isArray(payload.objects) ? payload.objects.length : 0;
            logToUi('INFO', `导出：元件 payload 已构建 objects=${count}`);
            const body = JSON.stringify(payload);
            logToUi('INFO', `导出：元件 请求发送 bytes=${body.length}`);
            return fetch('/api/shape_editor/export_gia_template', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json; charset=utf-8' },
                body
            });
        })
        .then(resp => resp.text().then(text => ({ resp, text })))
        .then(({ resp, text }) => {
            logToUi('INFO', `导出：元件 响应已收到 status=${resp.status}`);
            if (!resp.ok) {
                logToUi('ERROR', `导出为元件失败（HTTP ${resp.status}）`);
                logToUi('ERROR', text);
                toastToUi('error', `导出为元件失败（HTTP ${resp.status}）`, 2600);
                return;
            }
            const obj = JSON.parse(text);
            _applyPersistedReferenceImagesFromResponse(obj);
            logToUi('INFO', `导出为元件完成：decorations=${obj.decorations_count}`);
            logToUi('INFO', `output_gia_file: ${obj.output_gia_file}`);
            logToUi('INFO', `exported_to: ${obj.exported_to}`);
            toastToUi('info', `导出为元件完成：${obj.decorations_count} 个装饰物`);
        })
        .catch(err => {
            const msg = (err && err.message) ? err.message : String(err);
            logToUi('ERROR', `导出为元件异常（可能是后端崩溃/断开连接）：${msg}`);
            toastToUi('error', '导出为元件异常（请看日志）', 2600);
            throw err;
        });
}

