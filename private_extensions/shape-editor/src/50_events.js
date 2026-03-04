// 事件监听
function setupEventListeners() {
    // 选中事件
    canvas.on('selection:created', () => { 
        updatePropPanel(); 
        updateLayerListUI();
        const target = canvas.getActiveObject();
        if (target && target.type === 'activeSelection') {
            target.lockSkewingX = true;
            target.lockSkewingY = true;
        }
    });
    canvas.on('selection:updated', () => { 
        updatePropPanel(); 
        updateLayerListUI();
        const target = canvas.getActiveObject();
        if (target && target.type === 'activeSelection') {
            target.lockSkewingX = true;
            target.lockSkewingY = true;
        }
    });
    canvas.on('selection:cleared', () => { 
        activeObject = null;
        document.getElementById('prop-container').classList.add('hidden');
        document.getElementById('no-selection').classList.remove('hidden');
        updateLayerListUI();
    });
    
    // 物体修改事件
    canvas.on('object:modified', (opt) => {
        updatePropInputs();
        saveToLocal();
        saveHistory();
        if (opt && opt.target && opt.target.type === 'activeSelection' && opt.target.getObjects) {
            opt.target.getObjects().forEach(obj => {
                obj.set({ skewX: 0, skewY: 0 });
                obj.setCoords();
            });
            canvas.requestRenderAll();
        }
    });
    
    canvas.on('object:added', () => { scheduleRenderLayerList(); });
    canvas.on('object:removed', () => { scheduleRenderLayerList(); });
    canvas.on('mouse:down', handlePickFromImage);
    
    // 中键拖拽平移（使用原生事件确保可触发）
    const upperCanvas = canvas.upperCanvasEl;
    if (upperCanvas) {
        upperCanvas.addEventListener('mousedown', (e) => {
            if (e.button !== 1) return;
            e.preventDefault();
            startPanning(e);
        });
    }
    setupPaintBrushTool();
    setupAltDuplicateDrag();
    setupPsLikeRotateDrag();
    setupBlankDragCreateRect();
    setupRightClickPickMenu();
    window.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        const vpt = canvas.viewportTransform;
        vpt[4] += e.clientX - lastPosX;
        vpt[5] += e.clientY - lastPosY;
        canvas.requestRenderAll();
        lastPosX = e.clientX;
        lastPosY = e.clientY;
    });
    window.addEventListener('mouseup', () => {
        stopPanning();
    });
    window.addEventListener('blur', () => {
        stopPanning();
        _cancelTransientInteractions();
    });
    canvas.on('mouse:wheel', (opt) => {
        const delta = opt.e.deltaY;
        let zoom = canvas.getZoom();
        zoom *= Math.pow(0.999, delta);
        zoom = Math.min(4, Math.max(0.2, zoom));
        const pointer = canvas.getPointer(opt.e);
        canvas.zoomToPoint(new fabric.Point(pointer.x, pointer.y), zoom);
        opt.e.preventDefault();
        opt.e.stopPropagation();
    });

    // 属性面板输入框
    const inputs = ['prop-x', 'prop-y', 'prop-w', 'prop-h', 'prop-angle', 'prop-scale'];
    inputs.forEach(id => {
        document.getElementById(id).addEventListener('change', applyProps);
    });

    // 图层按钮 (修改后需要刷新列表和历史)
    const layerAction = (action) => {
        const obj = canvas.getActiveObject();
        if (obj) {
            canvas[action](obj);
            saveToLocal();
            saveHistory(); // 层级改变也算历史
            renderLayerList();
        }
    }
    document.getElementById('layer-up').onclick = () => layerAction('bringForward');
    document.getElementById('layer-down').onclick = () => layerAction('sendBackwards');
    document.getElementById('layer-top').onclick = () => layerAction('bringToFront');
    document.getElementById('layer-bottom').onclick = () => layerAction('sendToBack');
    const timelapseBtn = document.getElementById('btn-layer-timelapse');
    if (timelapseBtn && typeof playLayerTimelapseReveal === 'function') {
        timelapseBtn.onclick = () => { playLayerTimelapseReveal(); };
    }

    // 删除与打组
    document.getElementById('btn-delete').onclick = deleteSelected;
    document.getElementById('btn-group').onclick = groupSelected;
    document.getElementById('btn-ungroup').onclick = ungroupSelected;

    // 参考图操作
    document.getElementById('img-upload').addEventListener('change', handleImageUpload);
    document.getElementById('ref-opacity').addEventListener('input', (e) => {
        const obj = canvas.getActiveObject();
        if (obj && obj.type === 'image') {
            obj.set('opacity', parseFloat(e.target.value));
            canvas.requestRenderAll();
            // 实时拖动不一定要存历史，松手存？这里简单处理先不存
        }
    });
    // opacity input change 存历史
    document.getElementById('ref-opacity').addEventListener('change', () => {
         saveToLocal();
         saveHistory();
    });
    
    document.getElementById('btn-ref-back').onclick = () => layerAction('sendToBack');
    document.getElementById('btn-ref-front').onclick = () => layerAction('bringToFront');
    document.getElementById('btn-quantize-image').onclick = quantizeActiveImage;
    document.getElementById('pick-rect').onclick = () => setPickMode('rect');
    document.getElementById('pick-circle').onclick = () => setPickMode('circle');
    document.getElementById('pick-off').onclick = () => setPickMode('off');
    document.getElementById('paint-on').onclick = () => setPaintMode('brush');
    document.getElementById('paint-off').onclick = () => setPaintMode('off');
    const paintSizeEl = document.getElementById('paint-size');
    const paintSizeNumEl = document.getElementById('paint-size-number');
    if (paintSizeEl) {
        paintSizeEl.addEventListener('input', () => setPaintBrushSizePx(paintSizeEl.value));
        paintSizeEl.addEventListener('change', () => setPaintBrushSizePx(paintSizeEl.value));
    }
    if (paintSizeNumEl) {
        paintSizeNumEl.addEventListener('input', () => setPaintBrushSizePx(paintSizeNumEl.value));
        paintSizeNumEl.addEventListener('change', () => setPaintBrushSizePx(paintSizeNumEl.value));
    }
    document.getElementById('btn-del-ref').onclick = () => {
        const obj = canvas.getActiveObject();
        if (obj && obj.type === 'image') {
            canvas.remove(obj);
            saveToLocal();
            saveHistory();
        }
    };

    // 拖拽放置逻辑
    const wrapper = document.getElementById('canvas-wrapper');
    wrapper.addEventListener('dragover', (e) => {
        e.preventDefault(); // 允许放置
    });
    wrapper.addEventListener('drop', (e) => {
        e.preventDefault();
        const type = e.dataTransfer.getData('type');
        const color = e.dataTransfer.getData('color');
        
        if (type && color) {
            // 计算相对画布的坐标
            // 注意：Fabric canvas 内部可能有偏移，但 wrapper 是相对定位的容器
            // 简单计算：鼠标位置 - wrapper 位置 - 物体中心偏移
            const rect = wrapper.getBoundingClientRect();
            const left = e.clientX - rect.left - DEFAULT_SIZE / 2;
            const top = e.clientY - rect.top - DEFAULT_SIZE / 2;
            
            if (type === 'rect') {
                createRect(color, { left, top });
            } else if (type === 'circle') {
                createCircle(color, { left, top });
            }
        }
    });

    // 全局数据
    document.getElementById('btn-save').onclick = async () => {
        const payload = buildGiaExportPayload();
        const resp = await fetch('/api/shape_editor/project_canvas', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json; charset=utf-8'
            },
            body: JSON.stringify(payload)
        });
        const text = await resp.text();
        if (!resp.ok) {
            toastToUi('error', `保存失败（HTTP ${resp.status}）`, 2600);
            logToUi('ERROR', `保存失败（HTTP ${resp.status}）`);
            logToUi('ERROR', text);
            return;
        }
        const obj = JSON.parse(text);
        _applyPersistedReferenceImagesFromResponse(obj);
        toastToUi('info', '已保存到当前项目');
        logToUi('INFO', `已保存到当前项目：placement=${obj.placement_file || ''}`);
        // 若后端返回 rel_path，视为“当前激活实体”，下次启动应恢复到它
        if (obj && obj.rel_path) {
            _selectedPlacementRelPath = String(obj.rel_path || '').trim();
            renderProjectPlacementsList();
            await _persistLastOpenedPlacement(_selectedPlacementRelPath);
        } else {
            await _persistLastOpenedPlacement(String(_selectedPlacementRelPath || '').trim());
        }
    };
    document.getElementById('btn-load').onclick = async () => {
        await bootRestoreProjectCanvas();
    };
    document.getElementById('btn-clear').onclick = () => {
        canvas.clear();
        canvas.setBackgroundColor('transparent', canvas.renderAll.bind(canvas));
        saveToLocal();
        saveHistory();
        toastToUi('info', '已清空画布');
        logToUi('INFO', '已清空画布');
    };
    document.getElementById('btn-export-json').onclick = exportJSON;
    document.getElementById('btn-export-group').onclick = exportSelectedGroupJSON;
    document.getElementById('json-upload').addEventListener('change', importJSON);
}

function deleteSelected() {
    const active = canvas.getActiveObjects();
    if (active.length) {
        canvas.discardActiveObject();
        active.forEach(obj => canvas.remove(obj));
        saveToLocal();
        saveHistory();
    }
}

function groupSelected() {
    if (!canvas.getActiveObject()) return;
    if (canvas.getActiveObject().type !== 'activeSelection') return;
    
    const group = canvas.getActiveObject().toGroup();
    group.set('label', getNextLabel('group'));
    ensureObjectId(group);
    canvas.requestRenderAll();
    updatePropPanel(); 
    saveToLocal();
    saveHistory();
}

function ungroupSelected() {
    if (!canvas.getActiveObject()) return;
    if (canvas.getActiveObject().type !== 'group') return;
    
    canvas.getActiveObject().toActiveSelection();
    canvas.requestRenderAll();
    updatePropPanel();
    saveToLocal();
    saveHistory();
}

