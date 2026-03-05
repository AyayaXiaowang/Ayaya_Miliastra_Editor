async function refreshHeaderStatus() {
    const resp = await fetch('/api/shape_editor/status', { method: 'GET' });
    if (!resp.ok) {
        _setHeaderStatus('未连接');
        return;
    }
    const obj = await resp.json();
    if (!obj || !obj.ok) {
        _setHeaderStatus('未连接');
        return;
    }
    const pkg = String(obj.package_id || '').trim() || '-';
    _setHeaderStatus(`已连接 | package=${pkg}`);
}

let _placementCheckedRelPaths = new Set(); // rel_path strings (normalized with "/")
let _placementBatchExportRunning = false;

function _normalizePlacementRelPath(relPath) {
    return String(relPath || '').trim().replace(/\\/g, '/');
}

function _getFilteredPlacementsForCurrentQuery() {
    const searchEl = document.getElementById('placement-search');
    const q = _normalizeTextForSearch(searchEl ? searchEl.value : '');
    const items = Array.isArray(_placementsCache) ? _placementsCache : [];
    return items.filter(it => {
        if (!q) return true;
        const s = `${it.file_name || ''} ${it.name || ''} ${it.instance_id || ''}`;
        return _normalizeTextForSearch(s).includes(q);
    });
}

function _cleanupPlacementCheckedRelPathsByCache() {
    const items = Array.isArray(_placementsCache) ? _placementsCache : [];
    const exists = new Set(items.map(it => _normalizePlacementRelPath(it && it.rel_path ? it.rel_path : '')).filter(Boolean));
    const next = new Set();
    for (const rel of _placementCheckedRelPaths.values()) {
        const r = _normalizePlacementRelPath(rel);
        if (r && exists.has(r)) next.add(r);
    }
    _placementCheckedRelPaths = next;
}

function _syncPlacementCheckedIndicator() {
    const el = document.getElementById('placement-checked-indicator');
    if (!el) return;
    const n = _placementCheckedRelPaths ? _placementCheckedRelPaths.size : 0;
    el.textContent = n >= 2 ? `已勾选：${n}（右上角导出将批量）` : `已勾选：${n}`;

    // Hint header export behavior (batch when checked >= 2)
    const btnExportEntity = document.getElementById('btn-export-gia-entity');
    const btnExportTemplate = document.getElementById('btn-export-gia-template');
    if (btnExportEntity) {
        btnExportEntity.title = n >= 2 ? `已勾选 ${n} 项：将批量导出为实体` : '导出当前画布为实体';
    }
    if (btnExportTemplate) {
        btnExportTemplate.title = n >= 2 ? `已勾选 ${n} 项：将批量导出为元件` : '导出当前画布为元件';
    }
}

function _setPlacementBatchActionsDisabled(disabled) {
    const dis = !!disabled;
    const btnExportEntity = document.getElementById('btn-export-gia-entity');
    const btnExportTemplate = document.getElementById('btn-export-gia-template');
    const btnRefresh = document.getElementById('btn-refresh-placements');
    const btnNew = document.getElementById('btn-new-entity');
    const btnAll = document.getElementById('btn-placement-check-all');
    const btnNone = document.getElementById('btn-placement-check-none');
    const searchEl = document.getElementById('placement-search');
    if (btnExportEntity) btnExportEntity.disabled = dis;
    if (btnExportTemplate) btnExportTemplate.disabled = dis;
    if (btnRefresh) btnRefresh.disabled = dis;
    if (btnNew) btnNew.disabled = dis;
    if (btnAll) btnAll.disabled = dis;
    if (btnNone) btnNone.disabled = dis;
    if (searchEl) searchEl.disabled = dis;
}

async function refreshProjectPlacements() {
    _setPlacementStatus('加载中…');
    const resp = await fetch('/api/shape_editor/placement_catalog', { method: 'GET' });
    const text = await resp.text();
    if (!resp.ok) {
        _setPlacementStatus(`HTTP ${resp.status}`);
        return;
    }
    const obj = JSON.parse(text);
    const items = Array.isArray(obj.placements) ? obj.placements : [];
    _placementsCache = items;
    _cleanupPlacementCheckedRelPathsByCache();
    _setPlacementStatus(`count=${items.length}`);
    renderProjectPlacementsList();
}

function renderProjectPlacementsList() {
    const container = document.getElementById('placement-list');
    if (!container) return;
    container.innerHTML = '';

    const filtered = _getFilteredPlacementsForCurrentQuery();

    if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.style.color = 'var(--muted)';
        empty.style.fontSize = '12px';
        empty.textContent = '（无匹配条目）';
        container.appendChild(empty);
        _syncPlacementCheckedIndicator();
        return;
    }

    filtered.forEach(it => {
        const rel = _normalizePlacementRelPath(it && it.rel_path ? it.rel_path : '');
        if (!rel) return;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'placement-item' + (rel === _selectedPlacementRelPath ? ' selected' : '');
        btn.onclick = () => loadProjectPlacement(rel);
        btn.ondblclick = (ev) => {
            if (ev) {
                ev.preventDefault();
                ev.stopPropagation();
            }
            _placementRenameRelPath = rel;
            showPlacementRenameMenuAt(ev, {
                rel_path: _placementRenameRelPath,
                title: String(it.name || it.file_name || rel).trim()
            });
        };
        btn.oncontextmenu = (ev) => {
            if (ev) {
                ev.preventDefault();
                ev.stopPropagation();
            }
            _placementContextRelPath = rel;
            showPlacementMenuAt(ev, {
                rel_path: _placementContextRelPath,
                title: String(it.name || it.file_name || rel).trim()
            });
        };

        const chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.className = 'placement-check';
        chk.checked = _placementCheckedRelPaths && _placementCheckedRelPaths.has(rel);
        chk.addEventListener('click', (ev) => { if (ev) ev.stopPropagation(); });
        chk.addEventListener('dblclick', (ev) => { if (ev) ev.stopPropagation(); });
        chk.addEventListener('contextmenu', (ev) => {
            if (!ev) return;
            ev.preventDefault();
            ev.stopPropagation();
        });
        chk.addEventListener('change', () => {
            if (chk.checked) {
                _placementCheckedRelPaths.add(rel);
            } else {
                _placementCheckedRelPaths.delete(rel);
            }
            _syncPlacementCheckedIndicator();
        });
        btn.appendChild(chk);

        const title = document.createElement('div');
        title.className = 'placement-title';
        title.textContent = String(it.name || it.file_name || rel).trim() || '(unnamed)';
        btn.appendChild(title);

        const meta = document.createElement('div');
        meta.className = 'placement-meta';
        const deco = Number(it.decorations_count || 0);
        const hasCanvas = it && it.has_canvas_payload === true;
        meta.textContent = hasCanvas ? `deco=${deco}` : `deco=${deco} · 无画布`;
        btn.appendChild(meta);

        container.appendChild(btn);
    });
    _syncPlacementCheckedIndicator();
}

function hidePlacementMenu() {
    const menu = document.getElementById('placement-context-menu');
    if (!menu) return;
    menu.classList.remove('visible');
    _placementContextRelPath = '';
}

function hidePlacementRenameMenu() {
    const menu = document.getElementById('placement-rename-menu');
    if (!menu) return;
    menu.classList.remove('visible');
    _placementRenameRelPath = '';
}

function showPlacementMenuAt(ev, opts) {
    const menu = document.getElementById('placement-context-menu');
    if (!menu) return;
    const title = document.getElementById('placement-menu-title');
    if (title) {
        const t = opts && opts.title ? String(opts.title) : '';
        title.textContent = t ? `实体操作：${t}` : '实体操作';
    }
    menu.classList.add('visible');
    const rect = menu.getBoundingClientRect();
    const pos = _clampPickMenuToViewport(ev.clientX, ev.clientY, rect.width, rect.height);
    menu.style.left = `${pos.x}px`;
    menu.style.top = `${pos.y}px`;
}

function showPlacementRenameMenuAt(ev, opts) {
    const menu = document.getElementById('placement-rename-menu');
    if (!menu) return;
    const title = document.getElementById('placement-rename-title');
    const input = document.getElementById('placement-rename-input');
    const t = opts && opts.title ? String(opts.title) : '';
    if (title) {
        title.textContent = t ? `重命名：${t}` : '重命名实体';
    }
    if (input) {
        input.value = t || '';
    }

    menu.classList.add('visible');
    const rect = menu.getBoundingClientRect();
    const x = ev && ev.clientX !== undefined ? ev.clientX : (window.innerWidth / 2);
    const y = ev && ev.clientY !== undefined ? ev.clientY : (window.innerHeight / 2);
    const pos = _clampPickMenuToViewport(x, y, rect.width, rect.height);
    menu.style.left = `${pos.x}px`;
    menu.style.top = `${pos.y}px`;
    if (input) {
        setTimeout(() => {
            input.focus();
            input.select();
        }, 0);
    }
}

async function deletePlacementRelPath(relPath) {
    const rel = String(relPath || '').trim();
    if (!rel) return;

    const resp = await fetch('/api/shape_editor/entities/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ rel_path: rel })
    });
    const text = await resp.text();
    if (!resp.ok) {
        toastToUi('error', `删除失败（HTTP ${resp.status}）`, 2600);
        logToUi('ERROR', `删除失败（HTTP ${resp.status}）`);
        logToUi('ERROR', text);
        return;
    }
    toastToUi('info', '已删除实体');
    logToUi('INFO', `已删除实体：${rel}`);
    if (_selectedPlacementRelPath === rel) {
        _selectedPlacementRelPath = '';
        await _persistLastOpenedPlacement('');
        canvas.clear();
        canvas.setBackgroundColor('transparent', canvas.renderAll.bind(canvas));
        canvas.requestRenderAll();
    }
    await refreshProjectPlacements();
}

async function duplicatePlacementRelPath(relPath) {
    const rel = String(relPath || '').trim();
    if (!rel) return;

    const resp = await fetch('/api/shape_editor/entities/duplicate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ rel_path: rel })
    });
    const text = await resp.text();
    if (!resp.ok) {
        toastToUi('error', `复制失败（HTTP ${resp.status}）`, 2600);
        logToUi('ERROR', `复制失败（HTTP ${resp.status}）`);
        logToUi('ERROR', text);
        return;
    }
    const obj = JSON.parse(text);
    toastToUi('info', '已复制实体');
    logToUi('INFO', `已复制实体：${rel} -> ${obj.rel_path || ''}`);
    await refreshProjectPlacements();
    if (obj && obj.rel_path) {
        await loadProjectPlacement(String(obj.rel_path));
    }
}

async function renamePlacementRelPath(relPath, newName) {
    const rel = String(relPath || '').trim();
    const name = String(newName || '').trim();
    if (!rel) return;
    if (!name) {
        toastToUi('warn', '实体名称不能为空');
        return;
    }
    const resp = await fetch('/api/shape_editor/entities/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ rel_path: rel, name })
    });
    const text = await resp.text();
    if (!resp.ok) {
        toastToUi('error', `重命名失败（HTTP ${resp.status}）`, 2600);
        logToUi('ERROR', `重命名失败（HTTP ${resp.status}）`);
        logToUi('ERROR', text);
        return;
    }
    toastToUi('info', '已重命名实体');
    logToUi('INFO', `已重命名实体：${rel} -> ${name}`);
    await refreshProjectPlacements();
}

async function _restoreCanvasFromProjectPayload(payload) {
    // 只接受我们自己的 payload 结构
    if (!payload || !payload.objects) return false;
    const objects = payload.objects;
    if (!Array.isArray(objects)) return false;

    canvas.clear();
    canvas.setBackgroundColor('transparent', canvas.renderAll.bind(canvas));

    // 批量添加：抑制每个 canvas.add() 触发的 renderLayerList / saveHistory / saveToLocal，
    // 结束后统一执行一次，将 O(n²) DOM 操作降为 O(n)。
    beginBatch();

    const imageTasks = [];
    objects.forEach(o => {
        if (!o || typeof o !== 'object') return;
        const t = String(o.type || '').toLowerCase();
        const isRef = o.isReference === true || t === 'image';
        if (isRef) {
            if (t === 'image') {
                imageTasks.push(_restoreReferenceImageFromPayload(o));
            }
            return;
        }

        if (t === 'rect') {
            createRect(o.color, {
                left: o.left,
                top: o.top,
                width: o.width,
                height: o.height,
                angle: o.angle,
                opacity: o.opacity,
                label: o.label,
                id: o.id,
                isLocked: o.isLocked,
                select: false,
                persist: false
            });
            return;
        }
        if (t === 'circle') {
            createCircle(o.color, {
                left: o.left,
                top: o.top,
                width: o.width,
                height: o.height,
                angle: o.angle,
                opacity: o.opacity,
                label: o.label,
                id: o.id,
                isLocked: o.isLocked,
                select: false,
                persist: false
            });
            return;
        }
    });

    endBatch();

    if (imageTasks.length > 0) {
        await Promise.all(imageTasks);
    }
    canvas.requestRenderAll();
    applyLockStates();
    saveToLocal(false);
    saveHistory();
    return true;
}

async function loadProjectPlacement(relPath) {
    const rel = String(relPath || '').trim();
    if (!rel) return;
    _selectedPlacementRelPath = rel;
    renderProjectPlacementsList();
    _setPlacementStatus('读取…');
    const resp = await fetch(`/api/shape_editor/placement?rel_path=${encodeURIComponent(rel)}`, { method: 'GET' });
    const text = await resp.text();
    if (!resp.ok) {
        _setPlacementStatus(`HTTP ${resp.status}`);
        return;
    }
    const obj = JSON.parse(text);
    _setPlacementStatus(obj && obj.ok ? 'OK' : 'ERR');
    if (!obj || !obj.ok || !obj.canvas_payload) return;

    const payload = obj.canvas_payload;
    await _restoreCanvasFromProjectPayload(payload);
    await _persistLastOpenedPlacement(rel);
}

function _checkAllFilteredPlacements() {
    const filtered = _getFilteredPlacementsForCurrentQuery();
    filtered.forEach(it => {
        const rel = _normalizePlacementRelPath(it && it.rel_path ? it.rel_path : '');
        if (!rel) return;
        _placementCheckedRelPaths.add(rel);
    });
    renderProjectPlacementsList();
}

function _clearAllPlacementChecks() {
    _placementCheckedRelPaths.clear();
    renderProjectPlacementsList();
}

function _getCheckedPlacementRelPathsInCacheOrder() {
    const items = Array.isArray(_placementsCache) ? _placementsCache : [];
    const out = [];
    const seen = new Set();
    items.forEach(it => {
        const rel = _normalizePlacementRelPath(it && it.rel_path ? it.rel_path : '');
        if (!rel) return;
        if (!(_placementCheckedRelPaths && _placementCheckedRelPaths.has(rel))) return;
        if (seen.has(rel)) return;
        out.push(rel);
        seen.add(rel);
    });
    return out;
}

function _getPlacementItemByRelPath(relPath) {
    const rel = _normalizePlacementRelPath(relPath);
    if (!rel) return null;
    const items = Array.isArray(_placementsCache) ? _placementsCache : [];
    return items.find(it => it && _normalizePlacementRelPath(it.rel_path) === rel) || null;
}

async function _batchExportCheckedPlacements(kind) {
    const exportKind = String(kind || '').trim().toLowerCase() === 'template' ? 'template' : 'entity';
    if (_placementBatchExportRunning) {
        toastToUi('warn', '批量导出进行中，请稍候…', 1800);
        return;
    }

    const relPaths = _getCheckedPlacementRelPathsInCacheOrder();
    if (relPaths.length === 0) {
        toastToUi('warn', '请先在实体列表勾选要导出的条目', 2000);
        return;
    }

    const exportUrl = exportKind === 'template' ? '/api/shape_editor/export_gia_template' : '/api/shape_editor/export_gia_entity';
    const verb = exportKind === 'template' ? '元件' : '实体';

    _placementBatchExportRunning = true;
    _setPlacementBatchActionsDisabled(true);
    _setPlacementStatus(`批量导出${verb}…`);

    logToUi('INFO', `批量导出开始：kind=${exportKind} count=${relPaths.length}`);
    toastToUi('info', `批量导出开始：${relPaths.length} 项（${verb}）`, 1800);

    const stat = { okCount: 0, skipCount: 0, failCount: 0 };
    return Promise.resolve()
        .then(async () => {
            for (let i = 0; i < relPaths.length; i++) {
                const rel = relPaths[i];
                const item = _getPlacementItemByRelPath(rel);
                const title = String(item && (item.name || item.file_name) ? (item.name || item.file_name) : rel).trim() || rel;
                _setPlacementStatus(`批量导出${verb} ${i + 1}/${relPaths.length}`);

                logToUi('INFO', `批量导出：${title} (${i + 1}/${relPaths.length})`);

                const placementResp = await fetch(`/api/shape_editor/placement?rel_path=${encodeURIComponent(rel)}`, { method: 'GET' });
                const placementText = await placementResp.text();
                if (!placementResp.ok) {
                    logToUi('ERROR', `批量导出读取失败（HTTP ${placementResp.status}） rel=${rel} title=${title}`);
                    logToUi('ERROR', placementText);
                    stat.failCount += 1;
                    continue;
                }
                const placementObj = JSON.parse(placementText);
                if (!placementObj || !placementObj.ok) {
                    logToUi('ERROR', `批量导出读取失败（bad payload） rel=${rel} title=${title}`);
                    logToUi('ERROR', placementText);
                    stat.failCount += 1;
                    continue;
                }
                const dataObj = placementObj.data;
                const metaObj = dataObj && dataObj.metadata ? dataObj.metadata : null;
                const seObj = metaObj && metaObj.shape_editor ? metaObj.shape_editor : null;
                if (!seObj || typeof seObj !== 'object') {
                    logToUi('WARN', `批量导出跳过：非 shape-editor 实体（metadata.shape_editor 缺失） rel=${rel} title=${title}`);
                    stat.skipCount += 1;
                    continue;
                }
                const payload = placementObj.canvas_payload;
                if (!payload || typeof payload !== 'object') {
                    logToUi('ERROR', `批量导出读取失败：未找到 canvas_payload rel=${rel} title=${title}`);
                    stat.failCount += 1;
                    continue;
                }

                // Ensure export targets the correct placement for stable naming.
                if (!payload.meta || typeof payload.meta !== 'object') payload.meta = {};
                payload.meta.target_rel_path = rel;
                if (!payload.meta.coord_origin) payload.meta.coord_origin = 'center';
                if (!payload.meta.coord_y_axis) payload.meta.coord_y_axis = 'up';

                const body = JSON.stringify(payload);
                logToUi('INFO', `批量导出请求：${verb} bytes=${body.length} rel=${rel}`);
                const exportResp = await fetch(exportUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json; charset=utf-8' },
                    body
                });
                const exportText = await exportResp.text();
                if (!exportResp.ok) {
                    logToUi('ERROR', `批量导出失败（HTTP ${exportResp.status}） rel=${rel} title=${title}`);
                    logToUi('ERROR', exportText);
                    stat.failCount += 1;
                    continue;
                }
                const exportObj = JSON.parse(exportText);
                _applyPersistedReferenceImagesFromResponse(exportObj);
                stat.okCount += 1;
                logToUi('INFO', `批量导出成功：${title} decorations=${exportObj.decorations_count} output=${exportObj.output_gia_file}`);
            }
            return stat;
        })
        .then((s) => {
            _setPlacementStatus(`批量导出完成 ok=${s.okCount} skip=${s.skipCount} fail=${s.failCount}`);
            logToUi('INFO', `批量导出完成：kind=${exportKind} ok=${s.okCount} skip=${s.skipCount} fail=${s.failCount}`);
            toastToUi(s.failCount > 0 ? 'warn' : 'info', `批量导出完成：成功${s.okCount} 跳过${s.skipCount} 失败${s.failCount}`, 2600);
        })
        .finally(() => {
            _placementBatchExportRunning = false;
            _setPlacementBatchActionsDisabled(false);
            _syncPlacementCheckedIndicator();
        });
}

function _exportGiaEntityFromHeaderWithChecks() {
    const n = _placementCheckedRelPaths ? _placementCheckedRelPaths.size : 0;
    if (n >= 2) {
        return _batchExportCheckedPlacements('entity');
    }
    return exportGiaAsEntity();
}

function _exportGiaTemplateFromHeaderWithChecks() {
    const n = _placementCheckedRelPaths ? _placementCheckedRelPaths.size : 0;
    if (n >= 2) {
        return _batchExportCheckedPlacements('template');
    }
    return exportGiaAsTemplate();
}

function setupProjectPlacementsPanel() {
    const searchEl = document.getElementById('placement-search');
    if (searchEl) {
        searchEl.addEventListener('input', () => renderProjectPlacementsList());
    }
    const refreshBtn = document.getElementById('btn-refresh-placements');
    if (refreshBtn) {
        refreshBtn.onclick = () => refreshProjectPlacements();
    }
    const checkAllBtn = document.getElementById('btn-placement-check-all');
    if (checkAllBtn) checkAllBtn.onclick = () => _checkAllFilteredPlacements();
    const checkNoneBtn = document.getElementById('btn-placement-check-none');
    if (checkNoneBtn) checkNoneBtn.onclick = () => _clearAllPlacementChecks();

    const exportEntityBtn = document.getElementById('btn-export-gia-entity');
    if (exportEntityBtn) exportEntityBtn.onclick = _exportGiaEntityFromHeaderWithChecks;
    const exportTemplateBtn = document.getElementById('btn-export-gia-template');
    if (exportTemplateBtn) exportTemplateBtn.onclick = _exportGiaTemplateFromHeaderWithChecks;
    const newBtn = document.getElementById('btn-new-entity');
    if (newBtn) {
        newBtn.onclick = async () => {
            const resp = await fetch('/api/shape_editor/entities/new', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json; charset=utf-8' },
                body: JSON.stringify({})
            });
            const text = await resp.text();
            if (!resp.ok) {
                toastToUi('error', `新建实体失败（HTTP ${resp.status}）`, 2600);
                logToUi('ERROR', `新建实体失败（HTTP ${resp.status}）`);
                logToUi('ERROR', text);
                return;
            }
            const obj = JSON.parse(text);
            toastToUi('info', '已新建空白实体');
            logToUi('INFO', `已新建空白实体：${obj.rel_path || ''}`);
            await refreshProjectPlacements();
            if (obj && obj.rel_path) {
                await loadProjectPlacement(String(obj.rel_path));
            }
        };
    }

    const plcCancel = document.getElementById('placement-menu-cancel');
    if (plcCancel) plcCancel.onclick = () => hidePlacementMenu();
    const plcCopy = document.getElementById('placement-menu-copy');
    if (plcCopy) plcCopy.onclick = () => { duplicatePlacementRelPath(_placementContextRelPath); hidePlacementMenu(); };
    const plcDel = document.getElementById('placement-menu-delete');
    if (plcDel) plcDel.onclick = () => { deletePlacementRelPath(_placementContextRelPath); hidePlacementMenu(); };

    const renameMenu = document.getElementById('placement-rename-menu');
    if (renameMenu) {
        renameMenu.addEventListener('mousedown', (e) => { if (e) e.stopPropagation(); });
        renameMenu.addEventListener('click', (e) => { if (e) e.stopPropagation(); });
    }
    const rnCancel = document.getElementById('placement-rename-cancel');
    if (rnCancel) rnCancel.onclick = () => hidePlacementRenameMenu();
    const rnOk = document.getElementById('placement-rename-ok');
    if (rnOk) {
        rnOk.onclick = async () => {
            const input = document.getElementById('placement-rename-input');
            const name = input ? String(input.value || '').trim() : '';
            const rel = String(_placementRenameRelPath || '').trim();
            await renamePlacementRelPath(rel, name);
            hidePlacementRenameMenu();
        };
    }
    const rnInput = document.getElementById('placement-rename-input');
    if (rnInput) {
        rnInput.addEventListener('keydown', async (e) => {
            if (!e) return;
            if (e.key === 'Escape') {
                e.preventDefault();
                hidePlacementRenameMenu();
                return;
            }
            if (e.key === 'Enter') {
                e.preventDefault();
                const name = String(rnInput.value || '').trim();
                const rel = String(_placementRenameRelPath || '').trim();
                await renamePlacementRelPath(rel, name);
                hidePlacementRenameMenu();
            }
        });
    }

    document.addEventListener('click', () => { hidePlacementMenu(); hidePlacementRenameMenu(); });
    window.addEventListener('blur', () => { hidePlacementMenu(); hidePlacementRenameMenu(); });
    logToUi('INFO', 'Shape Editor ready.');
    _syncPlacementCheckedIndicator();
}

async function tryLoadProjectCanvas() {
    const resp = await fetch('/api/shape_editor/project_canvas', { method: 'GET' });
    if (!resp.ok) {
        logToUi('WARN', `项目画布加载失败（HTTP ${resp.status}）`);
        return;
    }
    const obj = await resp.json();
    if (!obj || !obj.ok) {
        logToUi('WARN', '项目画布加载失败（bad payload）');
        return;
    }
    if (!obj.has_data || !obj.canvas_payload) {
        logToUi('INFO', '项目无已保存画布：将继续使用本地存储（若存在）');
        return;
    }

    const payload = obj.canvas_payload;
    const restored = await _restoreCanvasFromProjectPayload(payload);
    if (!restored) return;
    toastToUi('info', '已从当前项目恢复画布');
    logToUi('INFO', `已从当前项目恢复画布：${obj.placement_file || ''}`);
}

