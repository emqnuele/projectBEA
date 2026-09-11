import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';

const UpdateContext = createContext(null);

export function useUpdate() {
    const value = useContext(UpdateContext);
    if (!value) throw new Error('useUpdate must be used inside <UpdateProvider>');
    return value;
}

// the backend caches the answer for half an hour, so asking more often than
// this only costs a request that returns the same thing
const CHECK_EVERY = 30 * 60 * 1000;

// while a run is going the steps are the only thing moving on screen
const PROGRESS_EVERY = 900;

/**
 * Whether there is a new version, and the run that installs it.
 *
 * One place, because three things ask: the pill in the top bar, the panel on
 * the health screen, and the banner that appears once an update has landed and
 * she is still running the old code.
 */
export function UpdateProvider({ children }) {
    const [status, setStatus] = useState(null);
    const [run, setRun] = useState(null);
    const [checking, setChecking] = useState(false);
    // survives a page change, not a reload: the point is to stop the pill
    // reappearing on every navigation, not to hide an update forever
    const dismissed = useRef(new Set());
    const [, forceRender] = useState(0);

    const refresh = useCallback(async (force = false) => {
        setChecking(true);
        try {
            const next = await api.updateStatus(force);
            setStatus(next);
            if (next.run) setRun(next.run);
            return next;
        } catch {
            // the connection banner already says the brain is gone; an update
            // check failing on top of that is not news
            return null;
        } finally {
            setChecking(false);
        }
    }, []);

    useEffect(() => {
        refresh();
        const timer = setInterval(() => refresh(), CHECK_EVERY);
        return () => clearInterval(timer);
    }, [refresh]);

    // --- the run in flight ---
    useEffect(() => {
        if (run?.state !== 'running') return undefined;
        const timer = setInterval(async () => {
            try {
                const next = await api.updateRun();
                setRun(next);
                if (next?.state === 'done') refresh(true);
            } catch { /* the next tick will try again */ }
        }, PROGRESS_EVERY);
        return () => clearInterval(timer);
    }, [run?.state, refresh]);

    const start = useCallback(async () => {
        const started = await api.startUpdate();
        setRun(started);
        return started;
    }, []);

    const resolve = useCallback(async (name, choice) => {
        const result = await api.resolveReview(name, choice);
        setStatus((prev) => (prev ? { ...prev, reviews: result.reviews } : prev));
        return result;
    }, []);

    const dismiss = useCallback((sha) => {
        dismissed.current.add(sha);
        forceRender((n) => n + 1);
    }, []);

    const value = useMemo(() => {
        const report = run?.report || null;
        return {
            status,
            run,
            report,
            checking,
            available: Boolean(status?.available) && !dismissed.current.has(status?.latest),
            running: run?.state === 'running',
            // she is on the new code on disk, not in memory, until she restarts
            restartRequired: Boolean(report?.restart_required && report.status === 'updated'),
            reviews: status?.reviews || [],
            refresh,
            start,
            resolve,
            dismiss,
        };
    }, [status, run, checking, refresh, start, resolve, dismiss]);

    return <UpdateContext.Provider value={value}>{children}</UpdateContext.Provider>;
}
