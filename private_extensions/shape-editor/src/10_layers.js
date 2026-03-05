// 图层列表渲染（含大规模虚拟滚动优化）
//
// 当图层数量 <= _VL_THRESHOLD 时，使用传统 DOM 直接渲染；
// 超过阈值后切换为"虚拟滚动"：仅渲染视口可见的 ~30-50 个条目，
// 用定高容器撑出滚动条，避免 1000+ DOM 节点导致的严重卡顿。

// ---- 虚拟滚动常量 ----
const _VL_ITEM_HEIGHT = 42;  // 每个条目槽高（item 36px + gap 6px）
const _VL_THRESHOLD   = 80;  // 超过此数量启用虚拟滚动
const _VL_BUFFER      = 8;   // 视口上下额外渲染的缓冲条目数

// ---- 虚拟滚动状态 ----
let _vlData = null;              // { filtered, orderMap, autoNameMap }
let _vlListenerAttached = false;
let _vlRafId = 0;
let _vlRenderedRange = null;     // { start, end } | null

function renderLayerList() {
    if (isBatching()) return;

    // 取消已排队的 debounced render
    if (_renderLayerListRafId) {
        cancelAnimationFrame(_renderLayerListRafId);
        _renderLayerListRafId = 0;
    }

    const listEl = document.getElementById('layer-list');

    // ---- 计算数据（与原逻辑一致） ----
    const objects = canvas.getObjects().slice().reverse();
    const typeCounters = { rect: 0, circle: 0, image: 0, group: 0 };
    const autoNameMap = new Map();
    objects.forEach(obj => {
        ensureObjectId(obj);
        const key = obj.type in typeCounters ? obj.type : 'other';
        if (!typeCounters[key]) typeCounters[key] = 0;
        typeCounters[key] += 1;
        autoNameMap.set(obj, `${getTypeLabelPrefix(obj.type)}${typeCounters[key]}`);
    });
    const orderMap = new Map();
    objects.forEach((obj, i) => {
        orderMap.set(obj, objects.length - i);
    });
    const filtered = objects.filter(obj => {
        const displayIndex = orderMap.get(obj);
        return objectMatchesShape(obj, layerFilters.shape)
            && objectMatchesColor(obj, layerFilters.color)
            && objectMatchesSearch(obj, displayIndex, autoNameMap);
    });

    _layerListOrderIds = filtered.map(o => String(o.id || '')).filter(Boolean);

    // 更新图层计数指示器
    _vlUpdateCountIndicator(filtered.length, objects.length);

    // ---- 空列表 ----
    if (filtered.length === 0) {
        _vlCleanup(listEl);
        listEl.innerHTML = '<div class="text-gray-500 text-xs text-center mt-4">空空如也</div>';
        return;
    }

    // ---- 小规模：直接渲染 ----
    if (filtered.length <= _VL_THRESHOLD) {
        _vlCleanup(listEl);
        _renderLayerListDirect(listEl, filtered, orderMap, autoNameMap);
        return;
    }

    // ---- 大规模：虚拟滚动 ----
    _vlData = { filtered, orderMap, autoNameMap };
    _vlRenderedRange = null; // 强制重绘（数据可能已变，如选中状态更新）
    _vlEnsureScrollListener(listEl);
    _vlRenderVisible(listEl);
}

// ---- 计数指示器 ----
function _vlUpdateCountIndicator(filteredCount, totalCount) {
    const el = document.getElementById('layer-count-indicator');
    if (!el) return;
    if (totalCount === 0) {
        el.textContent = '';
    } else if (filteredCount === totalCount) {
        el.textContent = `${totalCount}`;
    } else {
        el.textContent = `${filteredCount}/${totalCount}`;
    }
}

// ---- 清理虚拟滚动状态（切回直接模式时调用） ----
function _vlCleanup(listEl) {
    _vlData = null;
    _vlRenderedRange = null;
    listEl.style.display = '';
}

// ---- 直接渲染（小规模列表，保留原有拖拽排序能力） ----
function _renderLayerListDirect(listEl, filtered, orderMap, autoNameMap) {
    listEl.innerHTML = '';
    filtered.forEach(obj => {
        const item = _buildLayerItem(obj, orderMap, autoNameMap, true);
        listEl.appendChild(item);
    });
}

// ---- 虚拟滚动：挂载 scroll 监听 ----
function _vlEnsureScrollListener(listEl) {
    if (_vlListenerAttached) return;
    _vlListenerAttached = true;
    listEl.addEventListener('scroll', () => {
        if (!_vlData) return;
        if (_vlRafId) return;
        _vlRafId = requestAnimationFrame(() => {
            _vlRafId = 0;
            const el = document.getElementById('layer-list');
            if (el) _vlRenderVisible(el);
        });
    }, { passive: true });
}

// ---- 虚拟滚动：渲染可见区域 ----
function _vlRenderVisible(listEl) {
    if (!_vlData) return;
    const { filtered, orderMap, autoNameMap } = _vlData;
    const totalCount = filtered.length;
    const totalHeight = totalCount * _VL_ITEM_HEIGHT;

    const scrollTop = listEl.scrollTop;
    const viewportH = listEl.clientHeight || 400;

    const startIdx = Math.max(0, Math.floor(scrollTop / _VL_ITEM_HEIGHT) - _VL_BUFFER);
    const endIdx = Math.min(totalCount, Math.ceil((scrollTop + viewportH) / _VL_ITEM_HEIGHT) + _VL_BUFFER);

    // 仅滚动事件触发时：如果可见范围未变则跳过
    if (_vlRenderedRange && _vlRenderedRange.start === startIdx && _vlRenderedRange.end === endIdx) {
        return;
    }
    _vlRenderedRange = { start: startIdx, end: endIdx };

    // 获取或创建定高容器（保持 scrollTop 稳定）
    let container = listEl.querySelector('.vl-container');
    if (!container) {
        listEl.innerHTML = '';
        listEl.style.display = 'block';
        container = document.createElement('div');
        container.className = 'vl-container';
        container.style.position = 'relative';
        listEl.appendChild(container);
    }
    container.style.height = `${totalHeight}px`;

    // 用 fragment 一次性替换可见条目
    const fragment = document.createDocumentFragment();
    for (let i = startIdx; i < endIdx; i++) {
        const obj = filtered[i];
        const item = _buildLayerItem(obj, orderMap, autoNameMap, false);
        item.style.position = 'absolute';
        item.style.top = `${i * _VL_ITEM_HEIGHT}px`;
        item.style.left = '0';
        item.style.right = '0';
        fragment.appendChild(item);
    }
    container.innerHTML = '';
    container.appendChild(fragment);
}

// ---- 构建单个图层条目 DOM ----
function _buildLayerItem(obj, orderMap, autoNameMap, enableDrag) {
    const item = document.createElement('div');
    item.className = 'layer-item';

    // 选中状态
    const activeObj = canvas.getActiveObject();
    let isSelected = false;
    if (activeObj === obj) isSelected = true;
    if (activeObj && activeObj.type === 'activeSelection' && activeObj.contains(obj)) isSelected = true;
    if (isSelected) item.classList.add('selected');
    if (obj.isLocked) item.classList.add('locked');

    // 预览色块
    const preview = document.createElement('div');
    preview.className = 'layer-preview';
    if (obj.type === 'image' || obj.type === 'group') {
        preview.style.backgroundColor = '#555';
        preview.innerText = obj.type === 'group' ? 'GRP' : 'IMG';
        preview.style.fontSize = '8px';
        preview.style.color = '#fff';
        preview.style.display = 'flex';
        preview.style.alignItems = 'center';
        preview.style.justifyContent = 'center';
    } else {
        preview.style.backgroundColor = obj.fill;
    }
    item.appendChild(preview);

    // 名称
    const name = document.createElement('div');
    name.className = 'layer-name';
    const displayIndex = orderMap.get(obj);
    name.innerText = getObjectDisplayName(obj, displayIndex, autoNameMap);
    item.appendChild(name);

    // 点击选择
    item.addEventListener('click', (ev) => {
        if (ev) { ev.preventDefault(); ev.stopPropagation(); }
        handleLayerListSelectionClick(obj, ev);
    });

    // 右键菜单
    item.oncontextmenu = (ev) => {
        if (ev) { ev.preventDefault(); ev.stopPropagation(); }
        handleLayerListContextMenu(obj, ev);
    };

    // 锁定按钮
    const lockBtn = document.createElement('div');
    lockBtn.className = 'layer-lock';
    lockBtn.innerText = obj.isLocked ? '锁' : '解';
    lockBtn.title = obj.isLocked ? '解锁图层' : '锁定图层';
    lockBtn.draggable = false;
    if (obj.isLocked) lockBtn.classList.add('active');
    lockBtn.onclick = (e) => {
        e.stopPropagation();
        setObjectLocked(obj, !obj.isLocked);
        saveToLocal();
        saveHistory();
        updatePropPanel();
        renderLayerList();
    };
    item.appendChild(lockBtn);

    // 拖拽排序（仅小规模列表启用；1000+ 条目拖拽排序无实际意义）
    item.draggable = !!enableDrag;
    if (enableDrag) {
        item.dataset.objectId = obj.id;
        item.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('text/plain', obj.id);
            e.dataTransfer.effectAllowed = 'move';
        });
        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            const rect = item.getBoundingClientRect();
            const isTop = e.clientY < rect.top + rect.height / 2;
            item.classList.toggle('drag-over-top', isTop);
            item.classList.toggle('drag-over-bottom', !isTop);
        });
        item.addEventListener('dragleave', () => {
            item.classList.remove('drag-over-top', 'drag-over-bottom');
        });
        item.addEventListener('drop', (e) => {
            e.preventDefault();
            item.classList.remove('drag-over-top', 'drag-over-bottom');
            const rect = item.getBoundingClientRect();
            const isTop = e.clientY < rect.top + rect.height / 2;
            const draggedId = e.dataTransfer.getData('text/plain');
            reorderLayerById(draggedId, obj.id, isTop ? 'above' : 'below');
        });
    }

    return item;
}

function updateLayerListUI() {
    renderLayerList();
}

function _getCanvasSelectionObjects() {
    const active = canvas.getActiveObject();
    if (!active) return [];
    if (active.type === 'activeSelection' && active.getObjects) {
        return active.getObjects() || [];
    }
    return [active];
}

function _isObjectInSelection(obj, selectionObjects) {
    if (!obj) return false;
    const list = Array.isArray(selectionObjects) ? selectionObjects : _getCanvasSelectionObjects();
    return list.includes(obj);
}

function _setCanvasSelectionObjects(objs, opts = {}) {
    const allowLockedMulti = false;
    const wantsToast = opts && opts.toastOnLockedMulti;

    const unique = [];
    const seen = new Set();
    (Array.isArray(objs) ? objs : []).forEach(o => {
        if (!o) return;
        ensureObjectId(o);
        const id = String(o.id || '');
        if (!id) return;
        if (seen.has(id)) return;
        seen.add(id);
        unique.push(o);
    });

    if (unique.length === 0) {
        canvas.discardActiveObject();
        canvas.requestRenderAll();
        updatePropPanel();
        updateLayerListUI();
        return;
    }

    // 多选时默认排除锁定图层，避免出现"选中了但无法移动/变换"的混乱状态
    let candidates = unique;
    if (!allowLockedMulti && unique.length >= 2) {
        const locked = unique.filter(o => o && o.isLocked);
        candidates = unique.filter(o => o && !o.isLocked);
        if (locked.length > 0 && wantsToast) {
            toastToUi('warn', '锁定图层不参与 Ctrl/Shift 多选（可单独点选）', 2000);
        }
        if (candidates.length === 0) {
            // 全是锁定：退化为单选第一个
            candidates = [unique[0]];
        }
    }

    if (candidates.length === 1) {
        const obj = candidates[0];
        if (obj.isLocked) {
            // 允许在右侧列表单选锁定图层（用于查看/导出等），但不允许画布直接拖拽
            obj.selectable = true;
            canvas.setActiveObject(obj);
            obj.selectable = false;
        } else {
            canvas.setActiveObject(obj);
        }
        canvas.requestRenderAll();
        updatePropPanel();
        updateLayerListUI();
        return;
    }

    const selection = new fabric.ActiveSelection(candidates, { canvas });
    selection.lockSkewingX = true;
    selection.lockSkewingY = true;
    canvas.setActiveObject(selection);
    canvas.requestRenderAll();
    updatePropPanel();
    updateLayerListUI();
}

function _getObjectsByLayerIds(ids) {
    const arr = Array.isArray(ids) ? ids : [];
    const objects = [];
    arr.forEach(id => {
        const obj = getObjectById(String(id || ''));
        if (obj) objects.push(obj);
    });
    return objects;
}

function handleLayerListSelectionClick(obj, ev) {
    if (!obj) return;
    ensureObjectId(obj);
    const id = String(obj.id || '');

    const isCtrl = !!(ev && (ev.ctrlKey || ev.metaKey));
    const isShift = !!(ev && ev.shiftKey);

    const current = _getCanvasSelectionObjects();
    const hasAnchor = Boolean(_layerListAnchorId);

    // Shift：范围选择（锚点到当前）
    if (isShift && hasAnchor && _layerListOrderIds.length > 0) {
        const a = _layerListOrderIds.indexOf(String(_layerListAnchorId));
        const b = _layerListOrderIds.indexOf(id);
        if (a !== -1 && b !== -1) {
            const lo = Math.min(a, b);
            const hi = Math.max(a, b);
            const rangeIds = _layerListOrderIds.slice(lo, hi + 1);
            const rangeObjs = _getObjectsByLayerIds(rangeIds);
            if (isCtrl) {
                // Ctrl+Shift：把范围并入当前
                _setCanvasSelectionObjects([...current, ...rangeObjs], { toastOnLockedMulti: true });
            } else {
                _setCanvasSelectionObjects(rangeObjs, { toastOnLockedMulti: true });
            }
            return;
        }
        // 找不到锚点/当前：退化为单选
    }

    // Ctrl：切换选择
    if (isCtrl) {
        if (obj.isLocked) {
            _layerListAnchorId = id;
            _setCanvasSelectionObjects([obj], { toastOnLockedMulti: false });
            return;
        }
        const next = _isObjectInSelection(obj, current)
            ? current.filter(o => o !== obj)
            : [...current, obj];
        _layerListAnchorId = id;
        _setCanvasSelectionObjects(next, { toastOnLockedMulti: true });
        return;
    }

    // 普通点击：单选
    _layerListAnchorId = id;
    _setCanvasSelectionObjects([obj], { toastOnLockedMulti: false });
}

function handleLayerListContextMenu(obj, ev) {
    if (!obj) return;
    ensureObjectId(obj);
    const current = _getCanvasSelectionObjects();
    const alreadySelected = _isObjectInSelection(obj, current);
    if (!alreadySelected) {
        _layerListAnchorId = String(obj.id || '');
        _setCanvasSelectionObjects([obj], { toastOnLockedMulti: false });
    }
    const active = canvas.getActiveObject();
    _showSelectionMenuAt(ev, {
        canGroup: !!(active && active.type === 'activeSelection'),
        canUngroup: !!(active && active.type === 'group'),
        canSaveAs: !!active,
        canDelete: !!active
    });
    _hidePickMenu();
}

function getObjectById(id) {
    return canvas.getObjects().find(obj => obj.id === id);
}

function reorderLayerById(draggedId, targetId, position) {
    if (!draggedId || !targetId) return;
    if (draggedId === targetId) return;
    const dragged = getObjectById(draggedId);
    const target = getObjectById(targetId);
    if (!dragged || !target) return;

    const listOrder = canvas.getObjects().slice().reverse();
    const fromIndex = listOrder.indexOf(dragged);
    if (fromIndex === -1) return;
    listOrder.splice(fromIndex, 1);
    const targetIndex = listOrder.indexOf(target);
    if (targetIndex === -1) return;

    const insertIndex = position === 'above' ? targetIndex : targetIndex + 1;
    listOrder.splice(insertIndex, 0, dragged);

    const canvasOrder = listOrder.slice().reverse();
    canvasOrder.forEach((obj, index) => {
        canvas.moveTo(obj, index);
    });
    canvas.requestRenderAll();
    saveToLocal();
    saveHistory();
    renderLayerList();
}
