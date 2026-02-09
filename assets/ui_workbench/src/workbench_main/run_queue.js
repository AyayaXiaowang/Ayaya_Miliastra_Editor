// Global single-channel run queue for Workbench heavy operations.
//
// Why:
// - Avoid "multiple async chains write the same shared resources" (iframe/state/output panels).
// - Provide one coherent latest-wins / coalescing cancellation model via tokens.
//
// Design:
// - Single channel: only one task runs at a time.
// - Coalescing: tasks with same coalesceKey replace any pending one and invalidate older tokens.
// - No try/catch: fail-fast by design.
//
// NOTE: This queue is for "heavy ops" (validate/flatten/export/import/export_gil/gia).
// Preview variant switch (source/flattened) should remain a lightweight UI action.

function _safeTrim(v) {
    return String(v === undefined || v === null ? "" : v).trim();
}

function _nowMs() {
    return Date.now();
}

export function createRunQueue(opts) {
    var o = opts || {};
    var onStatus = typeof o.onStatus === "function" ? o.onStatus : null;
    var onDebug = typeof o.onDebug === "function" ? o.onDebug : null;

    // Pending task list (FIFO), but tasks may be coalesced (replaced) before execution.
    var _pending = [];
    var _running = false;

    // Global session (source context) to invalidate tasks across different coalesceKeys.
    // Example session key:
    // - "editor:<sourceHash>"
    // - "ui_source:<scope>:<rel_path>:<sourceHash>"
    var _sessionKey = "";
    var _sessionGeneration = 0;

    // coalesceKey -> generation number
    var _generationByKey = {};

    function _emitStatus(text) {
        if (!onStatus) return;
        onStatus(String(text || ""));
    }

    function _emitDebug(text) {
        if (!onDebug) return;
        onDebug(String(text || ""));
    }

    function _nextGenerationForKey(coalesceKey) {
        var k = _safeTrim(coalesceKey);
        if (!k) {
            return 0;
        }
        var prev = _generationByKey[k] || 0;
        var next = prev + 1;
        _generationByKey[k] = next;
        return next;
    }

    function _getGenerationForKey(coalesceKey) {
        var k = _safeTrim(coalesceKey);
        if (!k) return 0;
        return _generationByKey[k] || 0;
    }

    function _makeToken(coalesceKey, generation) {
        var k = _safeTrim(coalesceKey);
        var g = Number(generation || 0);
        var sessionGen = _sessionGeneration;
        var sessionKey = _sessionKey;
        var createdAtMs = _nowMs();
        return {
            coalesce_key: k,
            generation: g,
            session_key: sessionKey,
            session_generation: sessionGen,
            created_at_ms: createdAtMs,
            isActive: function () {
                // session invalidation (cross-op): any source-context change cancels old tasks.
                if (_sessionGeneration !== sessionGen) {
                    return false;
                }
                if (!k) {
                    // non-coalesced tasks: only governed by session generation
                    return true;
                }
                return _getGenerationForKey(k) === g;
            }
        };
    }

    function _removePendingTasksByCoalesceKey(coalesceKey) {
        var k = _safeTrim(coalesceKey);
        if (!k) return;
        if (_pending.length <= 0) return;
        var out = [];
        for (var i = 0; i < _pending.length; i++) {
            var t = _pending[i];
            if (!t) continue;
            if (String(t.coalesceKey || "") === k) {
                continue;
            }
            out.push(t);
        }
        _pending = out;
    }

    function enqueue(payload) {
        var p = payload || {};
        var label = _safeTrim(p.label) || "任务";
        var action = p.action;
        if (typeof action !== "function") {
            throw new Error("runQueue.enqueue: action 必须为 function");
        }
        var coalesceKey = _safeTrim(p.coalesceKey);
        var queuedAtMs = _nowMs();

        var generation = 0;
        var token = null;
        if (coalesceKey) {
            generation = _nextGenerationForKey(coalesceKey);
            token = _makeToken(coalesceKey, generation);
            _removePendingTasksByCoalesceKey(coalesceKey);
        } else {
            token = _makeToken("", 0);
        }

        var task = {
            label: label,
            coalesceKey: coalesceKey,
            token: token,
            queuedAtMs: queuedAtMs,
            startedAtMs: 0,
            finishedAtMs: 0,
            resolve: null,
            promise: null,
            action: action,
        };

        task.promise = new Promise(function (resolve) {
            task.resolve = resolve;
        });

        _pending.push(task);
        _drain();
        return task.promise;
    }

    function setSessionKey(sessionKey) {
        var k = _safeTrim(sessionKey);
        if (k === _sessionKey) {
            return _sessionGeneration;
        }
        _sessionKey = k;
        _sessionGeneration += 1;
        // Drop all pending tasks from previous sessions.
        _pending = [];
        _emitDebug("切换 session: " + _sessionKey + " (gen=" + String(_sessionGeneration) + ")");
        _drain();
        return _sessionGeneration;
    }

    function getSessionKey() {
        return _sessionKey;
    }

    function getSessionGeneration() {
        return _sessionGeneration;
    }

    function _drain() {
        if (_running) {
            return;
        }
        if (_pending.length <= 0) {
            return;
        }
        _running = true;
        // Run async without awaiting here, to keep API simple.
        _drainAsync();
    }

    async function _drainAsync() {
        while (_pending.length > 0) {
            var task = _pending.shift();
            if (!task) continue;

            // Skip stale tasks before start (session or coalesceKey).
            if (task.token && !task.token.isActive()) {
                _emitDebug("跳过过期任务: " + task.label);
                if (task.resolve) task.resolve({ skipped: true, reason: "stale_before_start" });
                continue;
            }

            task.startedAtMs = _nowMs();
            var startedAtMs = task.startedAtMs;
            _emitStatus(task.label + "…");

            // Execute
            var result = await task.action({
                token: task.token,
                label: task.label,
                queued_at_ms: task.queuedAtMs,
                started_at_ms: task.startedAtMs,
            });

            task.finishedAtMs = _nowMs();
            var cost = task.finishedAtMs - startedAtMs;
            _emitDebug("完成任务: " + task.label + " (" + String(cost) + "ms)");

            if (task.resolve) {
                task.resolve({ skipped: false, result: result });
            }
        }
        _running = false;
        // Clear operation status when idle.
        _emitStatus("");
    }

    function getQueueSize() {
        return _pending.length;
    }

    return {
        enqueue: enqueue,
        setSessionKey: setSessionKey,
        getSessionKey: getSessionKey,
        getSessionGeneration: getSessionGeneration,
        getQueueSize: getQueueSize,
    };
}

