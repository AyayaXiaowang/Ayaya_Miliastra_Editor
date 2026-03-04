// 图片参考逻辑
function handleImageUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function (f) {
        const data = f.target.result;
        fabric.Image.fromURL(data, function (img) {
            if (img.width > canvas.width) {
                img.scaleToWidth(canvas.width * 0.8);
            }
            img.set({
                opacity: 0.5,
                selectable: true,
                evented: true,
                isReference: true,
                label: getNextLabel('image'),
                id: getNewObjectId(),
                isLocked: false,
                lockSkewingX: true,
                lockSkewingY: true
            });
            // 项目级持久化后会回填稳定 src；新上传默认为空
            img.qxPersistedSrc = '';
            canvas.add(img);
            canvas.sendToBack(img);
            canvas.setActiveObject(img);
            e.target.value = '';
            saveToLocal();
            saveHistory();
        });
    };
    reader.readAsDataURL(file);
}

function getImageElement(img) {
    if (img.getElement) return img.getElement();
    return img._element || img._originalElement;
}

function _normalizeReferenceImageSrc(src) {
    const s = String(src || '').trim();
    if (!s) return '';
    if (s.startsWith('data:')) return s;
    if (s.startsWith('/')) return s;
    const origin = String(window.location.origin || '').trim();
    if (origin && s.startsWith(origin + '/')) {
        return s.slice(origin.length);
    }
    return s;
}

function getReferenceImageSrcForPayload(img) {
    if (!img) return '';
    const persisted = String(img.qxPersistedSrc || '').trim();
    if (persisted) return _normalizeReferenceImageSrc(persisted);

    let src = '';
    if (typeof img.getSrc === 'function') {
        src = String(img.getSrc() || '');
    } else {
        const el = getImageElement(img);
        src = el ? String(el.src || '') : '';
    }
    return _normalizeReferenceImageSrc(src);
}

function _applyPersistedReferenceImagesFromResponse(respObj) {
    const arr = respObj && Array.isArray(respObj.reference_images) ? respObj.reference_images : [];
    if (!arr || arr.length === 0) return;

    const map = new Map();
    arr.forEach(it => {
        if (!it || typeof it !== 'object') return;
        const id = String(it.id || '').trim();
        const src = _normalizeReferenceImageSrc(String(it.src || '').trim());
        if (!id || !src) return;
        map.set(id, src);
    });
    if (map.size === 0) return;

    canvas.getObjects().forEach(obj => {
        if (!obj || obj.type !== 'image') return;
        if (!obj.isReference) return;
        ensureObjectId(obj);
        const id = String(obj.id || '').trim();
        const src = map.get(id);
        if (!src) return;
        obj.qxPersistedSrc = src;
    });
}

function _restoreReferenceImageFromPayload(o) {
    return new Promise((resolve) => {
        const src0 = _normalizeReferenceImageSrc(String(o && o.src ? o.src : '').trim());
        if (!src0) {
            resolve(false);
            return;
        }
        const src = src0.startsWith('data:') ? src0 : encodeURI(src0);
        const left = _coerceFiniteNumber(o && o.left, 0);
        const top = _coerceFiniteNumber(o && o.top, 0);
        const width = _coerceFiniteNumber(o && o.width, 0);
        const height = _coerceFiniteNumber(o && o.height, 0);
        const angle = _coerceFiniteNumber(o && o.angle, 0);
        const opacity = _coerceFiniteNumber(o && o.opacity, 0.5);
        const label = String(o && o.label ? o.label : '').trim() || getNextLabel('image');
        const id = String(o && o.id ? o.id : '').trim() || getNewObjectId();
        const locked = o && o.isLocked === true;

        let finished = false;
        const timeoutMs = 4000;
        const timer = setTimeout(() => {
            if (finished) return;
            finished = true;
            resolve(false);
        }, timeoutMs);

        fabric.Image.fromURL(src, function (img) {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            if (!img) {
                resolve(false);
                return;
            }
            // 非等比缩放：用 payload 的最终显示尺寸回推 scaleX/scaleY
            const iw = Number(img.width || 0) || 1;
            const ih = Number(img.height || 0) || 1;
            const sx = width > 0 ? (width / iw) : 1.0;
            const sy = height > 0 ? (height / ih) : 1.0;

            img.set({
                left: left,
                top: top,
                originX: 'left',
                originY: 'top',
                scaleX: sx,
                scaleY: sy,
                angle: angle,
                opacity: opacity,
                selectable: true,
                evented: true,
                isReference: true,
                label: label,
                id: id,
                isLocked: locked,
                lockSkewingX: true,
                lockSkewingY: true
            });
            // 若来自项目持久化的稳定 path，则作为后续保存的优先 src（避免再次发送 base64）
            img.qxPersistedSrc = src0.startsWith('data:') ? '' : src0;

            canvas.add(img);
            canvas.sendToBack(img);
            if (locked) {
                setObjectLocked(img, true);
            }
            resolve(true);
        });
    });
}

function quantizeActiveImage() {
    const obj = canvas.getActiveObject();
    if (!obj || obj.type !== 'image') {
        toastToUi('warn', '请先选中参考图');
        logToUi('WARN', '颜色规整：未选中参考图');
        return;
    }
    quantizeImageObject(obj);
}

function quantizeImageObject(img) {
    const el = getImageElement(img);
    if (!el) return;

    const sourceWidth = el.naturalWidth || img.width;
    const sourceHeight = el.naturalHeight || img.height;
    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = sourceWidth;
    tempCanvas.height = sourceHeight;
    const ctx = tempCanvas.getContext('2d');
    ctx.drawImage(el, 0, 0, sourceWidth, sourceHeight);

    const imageData = ctx.getImageData(0, 0, sourceWidth, sourceHeight);
    const data = imageData.data;
    for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] === 0) continue;
        const nearest = getNearestPaletteColor(data[i], data[i + 1], data[i + 2]);
        const rgb = hexToRgb(nearest);
        data[i] = rgb.r;
        data[i + 1] = rgb.g;
        data[i + 2] = rgb.b;
    }
    ctx.putImageData(imageData, 0, 0);

    const dataUrl = tempCanvas.toDataURL('image/png');
    fabric.Image.fromURL(dataUrl, function (newImg) {
        newImg.set({
            left: img.left,
            top: img.top,
            scaleX: img.scaleX,
            scaleY: img.scaleY,
            angle: img.angle,
            opacity: img.opacity,
            selectable: true,
            evented: true,
            isReference: true,
            label: img.label || getNextLabel('image'),
            id: img.id || getNewObjectId(),
            isLocked: img.isLocked || false,
            originX: img.originX,
            originY: img.originY,
            lockSkewingX: true,
            lockSkewingY: true
        });
        // 图像内容已变化：强制下次项目保存时重新落盘
        newImg.qxPersistedSrc = '';
        canvas.remove(img);
        canvas.add(newImg);
        if (newImg.isLocked) {
            setObjectLocked(newImg, true);
        }
        canvas.setActiveObject(newImg);
        canvas.requestRenderAll();
        saveToLocal();
        saveHistory();
    });
}

function setPickMode(mode) {
    pickMode = mode;
    const rectBtn = document.getElementById('pick-rect');
    const circleBtn = document.getElementById('pick-circle');
    const offBtn = document.getElementById('pick-off');
    if (rectBtn) rectBtn.classList.toggle('active', mode === 'rect');
    if (circleBtn) circleBtn.classList.toggle('active', mode === 'circle');
    if (offBtn) offBtn.classList.toggle('active', mode === 'off');
}

function startPanning(e) {
    isPanning = true;
    canvas.selection = false;
    canvas.skipTargetFind = true;
    lastPosX = e.clientX;
    lastPosY = e.clientY;
    canvas.setCursor('grabbing');
}

function stopPanning() {
    if (!isPanning) return;
    isPanning = false;
    canvas.selection = true;
    canvas.skipTargetFind = false;
    canvas.setCursor('default');
}

function sampleColorFromImage(img, pointer) {
    const local = img.toLocalPoint(new fabric.Point(pointer.x, pointer.y), 'left', 'top');
    const x = Math.floor(local.x);
    const y = Math.floor(local.y);
    if (x < 0 || y < 0 || x >= img.width || y >= img.height) return null;

    const el = getImageElement(img);
    if (!el) return null;

    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = img.width;
    tempCanvas.height = img.height;
    const ctx = tempCanvas.getContext('2d');
    ctx.drawImage(el, 0, 0, img.width, img.height);
    const data = ctx.getImageData(x, y, 1, 1).data;
    if (data[3] === 0) return null;
    return rgbToHex(data[0], data[1], data[2]);
}

function handlePickFromImage(opt) {
    if (pickMode === 'off') return;
    if (!opt || !opt.e || opt.e.button !== 0) return;
    // 兼容“参考图锁定”后 evented=false 导致 opt.target 为空：改为用 containsPoint 找顶层参考图
    if (opt && opt.target && opt.target.type !== 'image') return;

    const pointer = canvas.getPointer(opt.e);
    const img = (opt && opt.target && opt.target.type === 'image') ? opt.target : _findTopmostImageAtPointer(pointer);
    if (!img) return;
    const color = sampleColorFromImage(img, pointer);
    if (!color) return;

    const rgb = hexToRgb(color);
    const paletteColor = pickMode === 'circle'
        ? getNearestCirclePaletteColor(rgb.r, rgb.g, rgb.b)
        : getNearestRectPaletteColor(rgb.r, rgb.g, rgb.b);

    if (pickMode === 'rect') {
        createRect(paletteColor, { left: pointer.x - DEFAULT_SIZE / 2, top: pointer.y - DEFAULT_SIZE / 2, select: false });
    } else if (pickMode === 'circle') {
        createCircle(paletteColor, { left: pointer.x - DEFAULT_SIZE / 2, top: pointer.y - DEFAULT_SIZE / 2, select: false });
    }
}

let _pickMenuLast = null;

function _hidePickMenu() {
    const menu = document.getElementById('pick-context-menu');
    if (!menu) return;
    menu.classList.remove('visible');
    _pickMenuLast = null;
}

function _hideSelectionMenu() {
    const menu = document.getElementById('selection-context-menu');
    if (!menu) return;
    menu.classList.remove('visible');
}

function _clampPickMenuToViewport(x, y, w, h) {
    const vw = Math.max(0, window.innerWidth || 0);
    const vh = Math.max(0, window.innerHeight || 0);
    let nx = Number(x || 0);
    let ny = Number(y || 0);
    if (nx + w > vw - 6) nx = Math.max(6, vw - w - 6);
    if (ny + h > vh - 6) ny = Math.max(6, vh - h - 6);
    nx = Math.max(6, nx);
    ny = Math.max(6, ny);
    return { x: nx, y: ny };
}

function _findTopmostImageAtPointer(pointer) {
    const p = new fabric.Point(pointer.x, pointer.y);
    const objects = canvas.getObjects();
    for (let i = objects.length - 1; i >= 0; i--) {
        const obj = objects[i];
        if (!obj || obj.type !== 'image') continue;
        if (!obj.isReference) continue;
        if (obj.containsPoint && obj.containsPoint(p)) {
            return obj;
        }
    }
    return null;
}

function _showPickMenuAt(ev, opts) {
    const canPick = !!(opts && opts.canPick);
    const paletteColor = opts ? opts.paletteColor : null;
    const rectColor = opts ? opts.rectColor : null;
    const circleColor = opts ? opts.circleColor : null;
    const pointer = opts ? opts.pointer : null;
    const menu = document.getElementById('pick-context-menu');
    if (!menu) return;
    const title = document.getElementById('pick-menu-title');
    const swatch = document.getElementById('pick-menu-swatch');
    const btnRect = document.getElementById('pick-menu-rect');
    const btnCircle = document.getElementById('pick-menu-circle');
    if (title) {
        title.textContent = canPick ? '取色创建' : '取色创建（请在参考图上右键）';
    }
    if (swatch) {
        swatch.style.backgroundColor = canPick ? String(paletteColor || '#000') : 'transparent';
    }
    if (btnRect) btnRect.disabled = !canPick;
    if (btnCircle) btnCircle.disabled = !canPick;

    menu.classList.add('visible');
    const rect = menu.getBoundingClientRect();
    const pos = _clampPickMenuToViewport(ev.clientX, ev.clientY, rect.width, rect.height);
    menu.style.left = `${pos.x}px`;
    menu.style.top = `${pos.y}px`;
    _pickMenuLast = canPick && pointer ? { paletteColor, rectColor, circleColor, pointer } : null;
}

function _showSelectionMenuAt(ev, opts) {
    const menu = document.getElementById('selection-context-menu');
    if (!menu) return;
    const canGroup = !!(opts && opts.canGroup);
    const canUngroup = !!(opts && opts.canUngroup);
    const canSaveAs = !!(opts && opts.canSaveAs);
    const canDelete = !!(opts && opts.canDelete);
    const btnGroup = document.getElementById('sel-menu-group');
    const btnUngroup = document.getElementById('sel-menu-ungroup');
    const btnDelete = document.getElementById('sel-menu-delete');
    const btnSaveAs = document.getElementById('sel-menu-saveas');
    if (btnGroup) btnGroup.disabled = !canGroup;
    if (btnUngroup) btnUngroup.disabled = !canUngroup;
    if (btnDelete) btnDelete.disabled = !canDelete;
    if (btnSaveAs) btnSaveAs.disabled = !canSaveAs;

    menu.classList.add('visible');
    const rect = menu.getBoundingClientRect();
    const pos = _clampPickMenuToViewport(ev.clientX, ev.clientY, rect.width, rect.height);
    menu.style.left = `${pos.x}px`;
    menu.style.top = `${pos.y}px`;
}

function _buildCanvasPayloadFromSelection(active) {
    if (!active) return null;
    let objects = null;
    if (active.type === 'group' && active.getObjects) {
        objects = active.getObjects();
    } else if (active.type === 'activeSelection' && active.getObjects) {
        objects = active.getObjects();
    }
    if (!Array.isArray(objects)) return null;

    return {
        meta: {
            timestamp: new Date().toISOString(),
            tool: 'qx-shape-editor',
            mode: 'selection_save_as',
            target_rel_path: ''
        },
        canvas: { width: canvas.getWidth(), height: canvas.getHeight() },
        objects: collectExportObjects(objects)
    };
}

async function saveSelectionAsNewEntity() {
    const active = canvas.getActiveObject();
    const canvasPayload = _buildCanvasPayloadFromSelection(active);
    if (!canvasPayload) {
        toastToUi('warn', '请先多选或选中一个组');
        logToUi('WARN', '另存为新实体：未选中 activeSelection/group');
        return;
    }
    const resp = await fetch('/api/shape_editor/entities/save_as', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ canvas_payload: canvasPayload })
    });
    const text = await resp.text();
    if (!resp.ok) {
        toastToUi('error', `另存为新实体失败（HTTP ${resp.status}）`, 2600);
        logToUi('ERROR', `另存为新实体失败（HTTP ${resp.status}）`);
        logToUi('ERROR', text);
        return;
    }
    const obj = JSON.parse(text);
    toastToUi('info', '已另存为新实体');
    logToUi('INFO', `已另存为新实体：${obj.rel_path || ''}`);
    await refreshProjectPlacements();
    if (obj && obj.rel_path) {
        await loadProjectPlacement(String(obj.rel_path));
    }
}

function setupRightClickPickMenu() {
    const menu = document.getElementById('pick-context-menu');
    if (!menu) return;
    const btnRect = document.getElementById('pick-menu-rect');
    const btnCircle = document.getElementById('pick-menu-circle');
    const btnCancel = document.getElementById('pick-menu-cancel');

    if (btnRect) {
        btnRect.onclick = () => {
            const ctx = _pickMenuLast;
            if (!ctx) return;
            const color = ctx.rectColor || ctx.paletteColor;
            createRect(color, { left: ctx.pointer.x - DEFAULT_SIZE / 2, top: ctx.pointer.y - DEFAULT_SIZE / 2 });
            _hidePickMenu();
        };
    }
    if (btnCircle) {
        btnCircle.onclick = () => {
            const ctx = _pickMenuLast;
            if (!ctx) return;
            const color = ctx.circleColor || ctx.paletteColor;
            createCircle(color, { left: ctx.pointer.x - DEFAULT_SIZE / 2, top: ctx.pointer.y - DEFAULT_SIZE / 2 });
            _hidePickMenu();
        };
    }
    if (btnCancel) btnCancel.onclick = () => _hidePickMenu();

    const selCancel = document.getElementById('sel-menu-cancel');
    if (selCancel) selCancel.onclick = () => _hideSelectionMenu();
    const selGroup = document.getElementById('sel-menu-group');
    if (selGroup) selGroup.onclick = () => { groupSelected(); _hideSelectionMenu(); };
    const selUngroup = document.getElementById('sel-menu-ungroup');
    if (selUngroup) selUngroup.onclick = () => { ungroupSelected(); _hideSelectionMenu(); };
    const selDelete = document.getElementById('sel-menu-delete');
    if (selDelete) selDelete.onclick = () => { deleteSelected(); _hideSelectionMenu(); };
    const selSaveAs = document.getElementById('sel-menu-saveas');
    if (selSaveAs) selSaveAs.onclick = () => { saveSelectionAsNewEntity(); _hideSelectionMenu(); };

    document.addEventListener('click', () => { _hidePickMenu(); _hideSelectionMenu(); });
    window.addEventListener('blur', () => { _hidePickMenu(); _hideSelectionMenu(); });
    document.addEventListener('keydown', (ev) => {
        if (!ev) return;
        if (String(ev.key || '') === 'Escape') { _hidePickMenu(); _hideSelectionMenu(); }
    });

    const upperCanvas = canvas.upperCanvasEl;
    if (!upperCanvas) return;
    upperCanvas.addEventListener('contextmenu', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();

        // Priority 1: selection operations (multi-select / group)
        const active = canvas.getActiveObject();
        if (active && (active.type === 'activeSelection' || active.type === 'group')) {
            _showSelectionMenuAt(ev, {
                canGroup: active.type === 'activeSelection',
                canUngroup: active.type === 'group',
                canSaveAs: true,
                canDelete: true
            });
            _hidePickMenu();
            return;
        }

        const pointer = canvas.getPointer(ev);
        const img = _findTopmostImageAtPointer(pointer);
        if (!img) {
            _showPickMenuAt(ev, { canPick: false, paletteColor: null, pointer });
            return;
        }
        const color = sampleColorFromImage(img, pointer);
        if (!color) {
            _showPickMenuAt(ev, { canPick: false, paletteColor: null, pointer });
            return;
        }
        const rgb = hexToRgb(color);
        const rectColor = getNearestRectPaletteColor(rgb.r, rgb.g, rgb.b);
        const circleColor = getNearestCirclePaletteColor(rgb.r, rgb.g, rgb.b);
        // 菜单展示以矩形支持色为准（按钮各自使用对应 palette）
        _showPickMenuAt(ev, { canPick: true, paletteColor: rectColor, rectColor, circleColor, pointer });
    });
}

