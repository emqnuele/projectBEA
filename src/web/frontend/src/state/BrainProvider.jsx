import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE, api } from '../api';

const BrainContext = createContext(null);

export function useBrain() {
    const value = useContext(BrainContext);
    if (!value) throw new Error('useBrain must be used inside <BrainProvider>');
    return value;
}

const EVENT_LIMIT = 400;
const STATUS_EVERY = 1500;
const OVERVIEW_EVERY = 8000;

/**
 * One connection to the brain for the whole app.
 *
 * Every page used to open its own EventSource and its own timer — chat polled
 * /status twice a second on top of it. Here the stream is opened once, the two
 * snapshots are polled in one place, and reachability is a piece of shared
 * state instead of a console message nobody sees.
 */
export function BrainProvider({ children }) {
    const [events, setEvents] = useState([]);
    const [streaming, setStreaming] = useState(false);
    const [status, setStatus] = useState(null);
    const [overview, setOverview] = useState(null);
    const [connection, setConnection] = useState('connecting');
    // a clock that only moves when we hear from the brain, so anything derived
    // from 'how long ago' stays a pure function of state
    const [now, setNow] = useState(() => Date.now() / 1000);

    const seen = useRef(new Set());

    const pushEvent = useCallback((event) => {
        if (!event || seen.current.has(event.id)) return;
        seen.current.add(event.id);
        setEvents((prev) => [event, ...prev].slice(0, EVENT_LIMIT));
    }, []);

    // --- the live feed ---
    useEffect(() => {
        let source;
        let pollTimer;

        const startPolling = () => {
            if (pollTimer) return;
            const tick = async () => {
                try {
                    const res = await fetch(`${API_BASE}/events?limit=${EVENT_LIMIT}`);
                    if (res.ok) (await res.json()).forEach(pushEvent);
                } catch { /* the connection banner already says it */ }
            };
            tick();
            pollTimer = setInterval(tick, 3000);
        };

        try {
            source = new EventSource(`${API_BASE}/events/stream?backlog=200`);
            source.onopen = () => setStreaming(true);
            source.onmessage = (message) => pushEvent(JSON.parse(message.data));
            source.onerror = () => {
                setStreaming(false);
                // EventSource retries by itself; only fall back if it never opened
                if (source.readyState === EventSource.CLOSED) startPolling();
            };
        } catch {
            startPolling();
        }

        return () => {
            source?.close();
            if (pollTimer) clearInterval(pollTimer);
        };
    }, [pushEvent]);

    // --- the snapshots ---
    const refreshStatus = useCallback(async (signal) => {
        try {
            setStatus(await api.status(signal));
            setNow(Date.now() / 1000);
            setConnection('online');
        } catch (e) {
            if (e.name !== 'AbortError') setConnection('offline');
        }
    }, []);

    const refreshOverview = useCallback(async (signal) => {
        try {
            const data = await api.overview(signal);
            setOverview(data);
            setConnection('online');
            return data;
        } catch (e) {
            if (e.name !== 'AbortError') setConnection('offline');
            return null;
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        refreshStatus(controller.signal);
        refreshOverview(controller.signal);
        const statusTimer = setInterval(() => refreshStatus(controller.signal), STATUS_EVERY);
        const overviewTimer = setInterval(() => refreshOverview(controller.signal), OVERVIEW_EVERY);
        return () => {
            controller.abort();
            clearInterval(statusTimer);
            clearInterval(overviewTimer);
        };
    }, [refreshStatus, refreshOverview]);

    // --- the controls that must work from anywhere ---
    const interrupt = useCallback(async () => {
        await api.interrupt();
        await refreshStatus();
    }, [refreshStatus]);

    const toggleSleep = useCallback(async () => {
        const sleeping = status?.is_sleeping;
        await (sleeping ? api.dreamWake() : api.dreamRun());
        await refreshStatus();
        await refreshOverview();
    }, [status?.is_sleeping, refreshStatus, refreshOverview]);

    const value = useMemo(() => ({
        events,
        streaming,
        status,
        now,
        overview,
        connection,
        isSpeaking: Boolean(status?.is_speaking),
        isSleeping: Boolean(status?.is_sleeping),
        activeSkills: status?.active_skills || [],
        refreshStatus,
        refreshOverview,
        interrupt,
        toggleSleep,
    }), [events, streaming, status, overview, connection, now, refreshStatus, refreshOverview, interrupt, toggleSleep]);

    return <BrainContext.Provider value={value}>{children}</BrainContext.Provider>;
}

/** Events narrowed to one concern, without another subscription. */
export function useEventFeed({ sources, categories, limit = 200 } = {}) {
    const { events, streaming } = useBrain();
    return useMemo(() => {
        let list = events;
        if (sources) list = list.filter((e) => sources.includes(e.source));
        if (categories) list = list.filter((e) => categories.includes(e.category));
        return { events: list.slice(0, limit), streaming };
    }, [events, sources, categories, limit, streaming]);
}
