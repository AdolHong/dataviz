const DATAVIZ_INTERACTIVE_WORKER_PROTOCOL = 'dataviz/interactive-worker/v1';

const serializeError = (error, transformId, code = 'interactive_transform_failed') => ({
  code:String(error?.code || code),
  name:String(error?.name || 'Error'),
  message:String(error?.message || error || 'browser-python failed'),
  stack:typeof error?.stack === 'string' ? error.stack : null,
  transform_id:transformId,
  runtime:'browser-python',
  worker:true,
});

let pyodidePromise = null;
let loadedIndexUrl = null;
const cancelledRequests = new Set();

const loadRuntime = async indexUrl => {
  if (pyodidePromise && loadedIndexUrl === indexUrl) return pyodidePromise;
  loadedIndexUrl = indexUrl;
  pyodidePromise = import(`${indexUrl.replace(/\/$/, '')}/pyodide.mjs`)
    .then(module => module.loadPyodide({indexURL:indexUrl}));
  return pyodidePromise;
};

const PYTHON_BRIDGE = String.raw`
import inspect
import json
import traceback
import js
import sys
from datetime import date, datetime

class DatavizContext:
    def __init__(self, payload, request_id):
        self.inputs = payload.get("inputs", {})
        self.query_inputs = payload.get("query_inputs", {})
        self.compute_params = payload.get("compute_params", {})
        self.selections = payload.get("selections", {})
        self._request_id = request_id

    def input(self, name):
        return self.inputs[name]

    def table(self, name):
        value = self.inputs[name]
        if isinstance(value, dict) and value.get("__datavizColumnarTable"):
            value = value.get("columns", {})
        try:
            import pandas as pd
        except ImportError:
            return value
        return pd.DataFrame(value)

    def progress(self, value=None, message=""):
        js.postMessage({
            "protocol": "dataviz/interactive-worker/v1",
            "type": "progress",
            "request_id": self._request_id,
            "value": value,
            "message": str(message),
        })

def _normalize(value):
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict(orient="records")
        except TypeError:
            return value.to_dict()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value

async def _dataviz_execute(code, entrypoint, payload_json, request_id):
    namespace = {}
    exec(code, namespace)
    candidate = namespace.get(entrypoint)
    if not callable(candidate):
        raise TypeError(f"browser-python entrypoint is not callable: {entrypoint}")
    context = DatavizContext(json.loads(payload_json), request_id)
    result = candidate(context)
    if inspect.isawaitable(result):
        result = await result
    return json.dumps(_normalize(result), ensure_ascii=False, allow_nan=False)
`;

const removeTree = (FS, path) => {
  try {
    FS.readdir(path).filter(name => name !== '.' && name !== '..').forEach(name => {
      const child = `${path}/${name}`;
      const mode = FS.stat(child).mode;
      if (FS.isDir(mode)) removeTree(FS, child);
      else FS.unlink(child);
    });
    FS.rmdir(path);
  } catch (_error) {
    // The Worker is terminated after every generation; cleanup is best effort.
  }
};

self.addEventListener('message', async event => {
  const request = event.data || {};
  if (request.protocol === DATAVIZ_INTERACTIVE_WORKER_PROTOCOL && request.type === 'cancel') {
    cancelledRequests.add(request.request_id);
    return;
  }
  if (request.protocol !== DATAVIZ_INTERACTIVE_WORKER_PROTOCOL || request.type !== 'execute') return;
  let payloadProxy;
  let dependencyRoot = null;
  try {
    const pyodide = await loadRuntime(request.index_url);
    if (request.cancel_buffer && typeof pyodide.setInterruptBuffer === 'function') {
      pyodide.setInterruptBuffer(request.cancel_buffer);
    }
    if (cancelledRequests.has(request.request_id)) {
      const error = new Error('browser-python execution was cancelled');
      error.name = 'AbortError';
      error.code = 'interactive_transform_cancelled';
      throw error;
    }
    const requirements = request.python_dependencies || [];
    if (requirements.length) {
      await pyodide.loadPackage('micropip');
      pyodide.globals.set('__dv_requirements', pyodide.toPy(requirements));
      try {
        await pyodide.runPythonAsync('import micropip\nawait micropip.install(__dv_requirements, keep_going=True)');
      } finally {
        pyodide.globals.get('__dv_requirements')?.destroy?.();
        pyodide.globals.delete('__dv_requirements');
      }
    }
    await pyodide.runPythonAsync(PYTHON_BRIDGE);
    const dependencyFiles = request.code_dependencies || {};
    dependencyRoot = `/tmp/dataviz-${String(request.transform_id || 'transform').replace(/[^A-Za-z0-9_.-]/g, '-')}-${request.request_id}`;
    pyodide.FS.mkdirTree(dependencyRoot);
    Object.entries(dependencyFiles).forEach(([relative, source]) => {
      const safe = String(relative).replaceAll('\\', '/').split('/').filter(
        part => part && part !== '.' && part !== '..'
      ).join('/');
      if (!safe) return;
      const target = `${dependencyRoot}/${safe}`;
      pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf('/')));
      pyodide.FS.writeFile(target, String(source), {encoding:'utf8'});
    });
    pyodide.globals.set('__dv_dependency_root', dependencyRoot);
    await pyodide.runPythonAsync(
      'import sys\n'
      + 'sys.path.insert(0, __dv_dependency_root) if __dv_dependency_root not in sys.path else None'
    );
    pyodide.globals.set('__dv_code', request.code || '');
    pyodide.globals.set('__dv_entrypoint', request.entrypoint || 'transform');
    pyodide.globals.set('__dv_payload', JSON.stringify(request.context || {}));
    pyodide.globals.set('__dv_request_id', request.request_id);
    try {
      payloadProxy = await pyodide.runPythonAsync(
        'await _dataviz_execute(__dv_code, __dv_entrypoint, __dv_payload, __dv_request_id)'
      );
      const output = JSON.parse(String(payloadProxy));
      self.postMessage({
        protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
        type:'result',
        request_id:request.request_id,
        output,
      });
    } finally {
      payloadProxy?.destroy?.();
      ['__dv_code', '__dv_entrypoint', '__dv_payload', '__dv_request_id'].forEach(name => {
        pyodide.globals.get(name)?.destroy?.();
        pyodide.globals.delete(name);
      });
      if (dependencyRoot) {
        pyodide.globals.set('__dv_dependency_root', dependencyRoot);
        await pyodide.runPythonAsync(
          'import sys\n'
          + 'sys.path.remove(__dv_dependency_root) if __dv_dependency_root in sys.path else None'
        );
        pyodide.globals.get('__dv_dependency_root')?.destroy?.();
        pyodide.globals.delete('__dv_dependency_root');
        removeTree(pyodide.FS, dependencyRoot);
      }
    }
  } catch (error) {
    self.postMessage({
      protocol:DATAVIZ_INTERACTIVE_WORKER_PROTOCOL,
      type:'error',
      request_id:request.request_id,
      error:serializeError(error, request.transform_id),
    });
  } finally {
    cancelledRequests.delete(request.request_id);
  }
});
