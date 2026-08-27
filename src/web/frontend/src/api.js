// The dashboard is served by the brain itself, so calls go to its own origin.
// In `npm run dev` there is no backend on the vite origin, so point at the default.
export const API_BASE =
    import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');

export class ApiError extends Error {
    constructor(message, { status = 0, url = '' } = {}) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.url = url;
    }
}

// Every failure used to end in console.error and a screen that kept lying.
// One place to turn a fetch into either data or an error worth showing.
export async function request(path, { method = 'GET', body, signal, raw } = {}) {
    const url = `${API_BASE}${path}`;
    let res;
    try {
        res = await fetch(url, {
            method,
            signal,
            headers: body instanceof FormData || body === undefined
                ? undefined
                : { 'Content-Type': 'application/json' },
            body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
        });
    } catch (e) {
        if (e.name === 'AbortError') throw e;
        throw new ApiError('The brain is not answering', { url });
    }

    if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
            const payload = await res.json();
            if (payload?.detail) {
                detail = Array.isArray(payload.detail)
                    ? payload.detail.map(d => d.msg || d).join(', ')
                    : payload.detail;
            }
        } catch { /* a non-JSON error body is still an error */ }
        throw new ApiError(detail, { status: res.status, url });
    }

    if (raw) return res;
    if (res.status === 204) return null;
    return res.json();
}

export const api = {
    health: () => request('/health'),
    status: (signal) => request('/status', { signal }),
    overview: (signal) => request('/overview', { signal }),

    config: () => request('/config'),
    saveConfig: (config) => request('/config', { method: 'POST', body: { config } }),

    // the schema the settings screens render themselves from
    settings: () => request('/settings'),
    settingsSection: (key) => request(`/settings/${encodeURIComponent(key)}`),
    saveSettings: (key, values) =>
        request(`/settings/${encodeURIComponent(key)}`, { method: 'POST', body: values }),

    history: () => request('/history'),
    chat: (message) => request('/chat', { method: 'POST', body: { message } }),
    audio: (blob, filename) => {
        const form = new FormData();
        form.append('file', blob, filename);
        return request('/audio', { method: 'POST', body: form });
    },
    interrupt: () => request('/interrupt', { method: 'POST' }),

    sessions: () => request('/sessions'),
    createSession: () => request('/sessions', { method: 'POST' }),
    activateSession: (id) => request(`/sessions/${encodeURIComponent(id)}/activate`, { method: 'POST' }),
    renameSession: (id, title) => request(`/sessions/${encodeURIComponent(id)}`, { method: 'PATCH', body: { title } }),
    deleteSession: (id) => request(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),

    skills: () => request('/skills'),
    toggleSkill: (name, enable) =>
        request(`/skills/${encodeURIComponent(name)}/toggle?enable=${enable}`, { method: 'POST' }),

    plan: () => request('/plan'),
    setDirective: (text) => request('/plan/directive', { method: 'POST', body: { text } }),
    addObjective: (text, detail = '') => request('/plan/objectives', { method: 'POST', body: { text, detail } }),
    updateObjective: (id, patch) => request(`/plan/objectives/${id}`, { method: 'PATCH', body: patch }),
    deleteObjective: (id) => request(`/plan/objectives/${id}`, { method: 'DELETE' }),
    reorderPlan: (ids) => request('/plan/order', { method: 'POST', body: { ids } }),
    resetPlan: () => request('/plan/reset', { method: 'POST' }),

    dreamRun: () => request('/dream/run', { method: 'POST' }),
    dreamWake: () => request('/dream/wake', { method: 'POST' }),
    saveMemory: () => request('/memory/save', { method: 'POST' }),

    people: () => request('/memory/people'),
    roster: (limit = 60) => request(`/memory/roster?limit=${limit}`),
    selfLore: () => request('/memory/self'),
    recall: (q, k = 8) => request(`/memory/search?q=${encodeURIComponent(q)}&k=${k}`),

    secrets: () => request('/secrets'),

    testLlm: () => request('/test/llm', { method: 'POST' }),
    testTts: () => request('/test/tts', { method: 'POST' }),
    testObs: () => request('/test/obs', { method: 'POST' }),
    audioDevices: () => request('/audio/devices'),
};
