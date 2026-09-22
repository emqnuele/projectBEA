import { useEffect, useRef } from 'react';
import { API_BASE } from '../api';
import { useStore } from '../store';

/**
 * SSE event stream hook.
 * Opens a single EventSource to /events/stream for live events.
 * Falls back to polling /events if SSE fails.
 */
export function useEventStream() {
    const pushEvent = useStore((s) => s.pushEvent);
    const setConnection = useStore((s) => s.setConnection);
    const setStreaming = useStore((s) => s.setStreaming);
    const pollingRef = useRef(null);
    const sourceRef = useRef(null);

    useEffect(() => {
        let pollTimer = null;

        const startPolling = () => {
            if (pollTimer) return;
            const tick = async () => {
                try {
                    const res = await fetch(`${API_BASE}/events?limit=50`);
                    if (res.ok) {
                        const data = await res.json();
                        data.forEach(pushEvent);
                    }
                } catch (e) { /* connection banner handles state */ }
            };
            tick();
            pollTimer = setInterval(tick, 3000);
        };

        try {
            const source = new EventSource(`${API_BASE}/events/stream?backlog=200`);
            sourceRef.current = source;
            source.onopen = () => {
                setStreaming(true);
                setConnection('online');
            };
            source.onmessage = (msg) => {
                try { pushEvent(JSON.parse(msg.data)); } catch {}
            };
            source.onerror = () => {
                setStreaming(false);
                if (source.readyState === EventSource.CLOSED) {
                    setConnection('offline');
                    startPolling();
                }
            };
        } catch {
            setConnection('offline');
            startPolling();
        }

        return () => {
            sourceRef.current?.close();
            if (pollTimer) clearInterval(pollTimer);
        };
    }, [pushEvent, setConnection, setStreaming]);
}

/**
 * Status polling hook.
 * Polls /status and /overview on intervals.
 */
export function useStatusPolling() {
    const setStatus = useStore((s) => s.setStatus);
    const setConnection = useStore((s) => s.setConnection);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await fetch(`${API_BASE}/status`);
                if (res.ok) {
                    const data = await res.json();
                    setStatus(data);
                    setConnection('online');
                }
            } catch {
                setConnection('offline');
            }
        };
        fetchStatus();
        const timer = setInterval(fetchStatus, 5000);
        return () => clearInterval(timer);
    }, [setStatus, setConnection]);
}
