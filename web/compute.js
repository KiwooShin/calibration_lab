// The same UI supports the local Python server and the static browser build.
const browserMode = document.documentElement.dataset.compute === 'browser';
let worker, sequence = 0;
const pending = new Map();

function failAll(message) {
  for (const task of pending.values()) task.reject(new Error(message));
  pending.clear();
  worker?.terminate();
  worker = null;
}

export async function compute(path, payload, progress = () => {}) {
  if (!browserMode) {
    const response = await fetch(path, payload === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Calibration failed');
    return data;
  }
  if (payload === undefined) {
    const response = await fetch(new URL('./demo.json', import.meta.url));
    if (!response.ok) throw new Error('Could not load the example. Reload the page to retry.');
    return response.json();
  }
  if (!worker) {
    worker = new Worker(new URL('./calibration-worker.js', import.meta.url), {type: 'module'});
    worker.onmessage = ({data}) => {
      const task = pending.get(data.id);
      if (!task) return;
      if (data.progress) { task.progress(data.progress); return; }
      pending.delete(data.id);
      if (data.error) task.reject(new Error(data.error));
      else task.resolve(data.result);
    };
    worker.onerror = () => failAll('The browser solver could not start. Check your connection and try again.');
    worker.onmessageerror = () => failAll('Could not read the browser solver result. Try again.');
  }
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, {resolve, reject, progress});
    worker.postMessage({id, path, payload});
  });
}
