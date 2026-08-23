import { useEffect, useRef, useState } from 'react';
import { API_BASE } from './api';

// Live event feed. Replaces polling /events every two seconds: the UI was always
// slightly stale and the brain paid for a request whether or not anything had
// happened. Falls back to polling if the stream cannot be opened at all.
export function useEvents(limit = 200) {
    const [events, setEvents] = useState([]);
    const [live, setLive] = useState(false);
    const seen = useRef(new Set());

    useEffect(() => {
        let source;
        let pollTimer;

        const add = (event) => {
            if (seen.current.has(event.id)) return;
            seen.current.add(event.id);
            setEvents(prev => [event, ...prev].slice(0, limit));
        };

        const startPolling = () => {
            const tick = async () => {
                try {
                    const res = await fetch(`${API_BASE}/events?limit=${limit}`);
                    (await res.json()).forEach(add);
                } catch (e) {
                    console.error('event poll failed', e);
                }
            };
            tick();
            pollTimer = setInterval(tick, 2000);
        };

        try {
            source = new EventSource(`${API_BASE}/events/stream?backlog=${limit}`);
            source.onopen = () => setLive(true);
            source.onmessage = (message) => add(JSON.parse(message.data));
            source.onerror = () => {
                setLive(false);
                // EventSource retries on its own; only fall back if it never opened
                if (source.readyState === EventSource.CLOSED && !pollTimer) startPolling();
            };
        } catch (e) {
            console.error('event stream unavailable, polling instead', e);
            startPolling();
        }

        return () => {
            if (source) source.close();
            if (pollTimer) clearInterval(pollTimer);
        };
    }, [limit]);

    return { events, live };
}
