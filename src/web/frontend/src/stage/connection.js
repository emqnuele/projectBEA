/**
 * The engine's side of the browser source.
 *
 * One EventSource, which reconnects on its own — that is the whole reason this
 * is SSE and not a WebSocket. A snapshot arrives first and says how she looks
 * right now; everything after it is a patch.
 */

export function connect({ onSnapshot, onPatch, onStatus }) {
    let source = null;

    const open = () => {
        source = new EventSource('/stage/stream');

        source.onopen = () => onStatus?.({ connected: true });

        source.onerror = () => {
            // EventSource retries by itself; say so rather than tearing it down
            onStatus?.({ connected: false });
        };

        source.onmessage = (event) => {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch {
                return;
            }
            if (payload.type === 'snapshot') onSnapshot?.(payload);
            else onPatch?.(payload);
        };
    };

    open();
    return () => source?.close();
}

export async function stageConfig() {
    try {
        const response = await fetch('/stage/config');
        if (!response.ok) return {};
        return await response.json();
    } catch {
        return {};
    }
}
