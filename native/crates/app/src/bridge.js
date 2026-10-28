(() => {
  let next = 1;
  const pending = new Map();
  window.mbdynNative = {
    call(op, payload = {}, timeoutMs = 0) {
      return new Promise((resolve, reject) => {
        const id = next++;
        const timer = timeoutMs > 0 ? setTimeout(() => {
          if (!pending.delete(id)) return;
          reject(new Error(`Native ${op} acknowledgement timed out.`));
        }, timeoutMs) : null;
        pending.set(id, {resolve, reject, timer});
        try { window.ipc.postMessage(JSON.stringify({id, op, payload})); }
        catch (error) { pending.delete(id); if (timer !== null) clearTimeout(timer); reject(error); }
      });
    },
    notify(op) { window.ipc.postMessage(JSON.stringify({id:0, op, payload:{}})); },
  };
  window.__mbdynNativeResolve = (id, response) => {
    const request = pending.get(id);
    if (!request) return;
    pending.delete(id);
    if (request.timer !== null) clearTimeout(request.timer);
    response.ok ? request.resolve(response.value || {}) : request.reject(new Error(response.error || "Native operation failed."));
  };
})();
