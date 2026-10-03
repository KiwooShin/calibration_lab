// Pinned runtime includes SciPy >= 1.16, required for accepted-iteration callbacks.
const indexURL = 'https://cdn.jsdelivr.net/pyodide/v314.0.2/full/';
let runtime;

async function initialize(progress) {
  progress('Preparing the browser solver. First use downloads Python and scientific libraries…');
  const {loadPyodide} = await import(`${indexURL}pyodide.mjs`);
  const py = await loadPyodide({indexURL});
  await py.loadPackage(['numpy', 'scipy']);
  const response = await fetch(new URL('./python-sources.json', import.meta.url));
  if (!response.ok) throw new Error('Could not load the calibration model');
  const sources = await response.json();
  py.FS.mkdirTree('/home/pyodide/calibration');
  for (const [name, source] of Object.entries(sources)) {
    py.FS.writeFile(`/home/pyodide/calibration/${name}`, source);
  }
  await py.runPythonAsync(`
import json
from calibration.dataset import simulate
from calibration.solver import calibrate
def browser_calibrate(path, payload):
    body = json.loads(payload)
    if path == '/api/demo':
        data, truth = simulate(**body)
        result = calibrate(data, 'synthetic', truth)
    else:
        result = calibrate(body)
    return json.dumps(result, allow_nan=False)
`);
  return py;
}

self.onmessage = async ({data: {id, path, payload}}) => {
  const progress = message => self.postMessage({id, progress: message});
  try {
    if (!runtime) runtime = initialize(progress).catch(error => {runtime = null; throw error;});
    const py = await runtime;
    progress('Calibrating in your browser. Only training frames update the model…');
    py.globals.set('request_path', path);
    py.globals.set('request_payload', JSON.stringify(payload));
    const result = await py.runPythonAsync('browser_calibrate(request_path, request_payload)');
    self.postMessage({id, result: JSON.parse(result)});
  } catch (error) {
    self.postMessage({id, error: `${error.message || error}\nCheck your connection and retry if the solver download failed.`});
  }
};
