// NodeOps Manager — API layer
// All requests are relative (Vite dev proxy: /api → localhost:8000)

const BASE = '';

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);

  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      msg = err.detail || err.message || msg;
    } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

const get  = (path)       => request('GET',    path);
const post = (path, body) => request('POST',   path, body);
const put  = (path, body) => request('PUT',    path, body);
const del  = (path)       => request('DELETE', path);

// ─── Accounts ────────────────────────────────────────────────────────────────
export const getAccounts        = () => get('/api/accounts');
export const createAccount      = (data) => post('/api/accounts', data);
export const updateAccount      = (id, data) => put(`/api/accounts/${id}`, data);
export const deleteAccount      = (id) => del(`/api/accounts/${id}`);
export const unbindAccountTask  = (id) => post(`/api/accounts/${id}/unbind-task`);
export const refreshCredits     = (id) => post(`/api/accounts/${id}/refresh-credits`);
export const loginAccount       = (id) => post(`/api/accounts/${id}/login`);
export const verifyOtp          = (id, code) => post(`/api/accounts/${id}/verify-otp`, { code });

// ─── Projects ─────────────────────────────────────────────────────────────────
export const getProjects        = () => get('/api/projects');
export const createProject      = (data) => post('/api/projects', data);
export const deleteProject      = (name) => del(`/api/projects/${encodeURIComponent(name)}`);
export const getProjectDetail   = (name) => get(`/api/projects/${encodeURIComponent(name)}`);

// ─── Tasks ────────────────────────────────────────────────────────────────────
export const getAllTasks         = () => get('/api/tasks');
export const getTasksForProject = (projectName) =>
  get(`/api/tasks/project/${encodeURIComponent(projectName)}`);
export const getTask            = (project, taskId) =>
  get(`/api/tasks/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}`);
export const createTask         = (data) => post('/api/tasks', data);
export const updateTask         = (project, taskId, data) =>
  put(`/api/tasks/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}`, data);
export const deleteTask         = (project, taskId) =>
  del(`/api/tasks/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}`);
export const startTask          = (project, taskId) =>
  post(`/api/tasks/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}/start`);
export const cancelTask         = (project, taskId) =>
  post(`/api/tasks/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}/cancel`);
export const createEmptySessionForTask = (project, taskId) =>
  post(`/api/tasks/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}/sessions/empty`);
export const getTaskMessages    = (project, taskId) =>
  get(`/api/tasks/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}/messages`);

// ─── Session History ──────────────────────────────────────────────────────────
export const getSessionHistory  = (project, taskId) =>
  get(`/api/sessions/history/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}`);
export const getSessionContent  = (project, taskId, sessionFile) =>
  get(
    `/api/sessions/history/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}/content` +
    `?session_file=${encodeURIComponent(sessionFile)}`
  );
export const sendSessionMessage = (sessionId, accountId, data) =>
  post(
    `/api/sessions/${encodeURIComponent(sessionId)}/message?account_id=${encodeURIComponent(accountId)}`,
    data
  );

// ─── Files ────────────────────────────────────────────────────────────────────
export const getFileTree        = (accountId, path = '') =>
  get(`/api/files/tree?account_id=${encodeURIComponent(accountId)}&path=${encodeURIComponent(path)}`);
export const getTaskFileTree    = (projectName, taskId, path = '') =>
  get(
    `/api/files/tree/task?project_name=${encodeURIComponent(projectName)}` +
    `&task_id=${encodeURIComponent(taskId)}&path=${encodeURIComponent(path)}`
  );
export const getFileContent     = (accountId, path) =>
  get(`/api/files/content?account_id=${encodeURIComponent(accountId)}&path=${encodeURIComponent(path)}`);

// ─── Overview ─────────────────────────────────────────────────────────────────
export const getOverview        = () => get('/api/overview');

// ─── SSE Helper ──────────────────────────────────────────────────────────────
// Returns an EventSource instance. Caller is responsible for cleanup.
export function createTaskEventSource(project, taskId) {
  return new EventSource(
    `/api/events/task/${encodeURIComponent(project)}/${encodeURIComponent(taskId)}`
  );
}

// ─── Register (NodeOps) ──────────────────────────────────────────────────────
export const registerGmailBatch = (data) => post('/api/register/gmail-batch', data);

// Stream register logs from backend SSE endpoint.
// handlers: { onEvent?, onLog?, onResult?, onEnd? }
export async function registerGmailBatchStream(data, handlers = {}) {
  const res = await fetch(`${BASE}/api/register/gmail-batch/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {}),
  });

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      msg = err.detail || err.message || msg;
    } catch (_) {}
    throw new Error(msg);
  }

  if (!res.body) {
    throw new Error('Streaming response body is empty');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let finalResult = null;

  const emit = (eventName, payload) => {
    handlers.onEvent?.(eventName, payload);
    if (eventName === 'log') handlers.onLog?.(payload);
    if (eventName === 'result') {
      finalResult = payload;
      handlers.onResult?.(payload);
    }
    if (eventName === 'end') handlers.onEnd?.(payload);
    if (eventName === 'error') {
      const msg = payload?.message || payload?.error || 'register stream error';
      throw new Error(msg);
    }
  };

  const parseChunk = (raw) => {
    const lines = raw.split(/\r?\n/);
    let eventName = 'message';
    const dataLines = [];
    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim() || 'message';
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (!dataLines.length) return;
    const joined = dataLines.join('\n');
    let payload = joined;
    try {
      payload = JSON.parse(joined);
    } catch (_) {}
    emit(eventName, payload);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep = buffer.search(/\r?\n\r?\n/);
    while (sep !== -1) {
      const m = buffer.match(/\r?\n\r?\n/);
      const delimiterLen = m ? m[0].length : 2;
      const raw = buffer.slice(0, sep).trim();
      buffer = buffer.slice(sep + delimiterLen);
      if (raw) parseChunk(raw);
      sep = buffer.search(/\r?\n\r?\n/);
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    parseChunk(buffer.trim());
  }

  return finalResult;
}
