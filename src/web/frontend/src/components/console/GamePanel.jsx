import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Hand, Square } from 'lucide-react';
import { api } from '../../api';
import { Glass } from '../glass/Glass';
import { Button } from '../ui/controls';
import { Badge } from '../ui/feedback';
import { useToast } from '../../state/ToastProvider';

const POLL_MS = 2000;

// only three answers: busy, idle, or not there at all
const STATES = {
    busy: { label: 'playing', color: 'var(--flux-act)' },
    idle: { label: 'standing still', color: 'var(--text-dim)' },
    off: { label: 'not in the game', color: 'var(--text-dim)' },
};

function elapsed(seconds) {
    const whole = Math.max(0, Math.round(seconds || 0));
    if (whole < 60) return `${whole}s`;
    return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, '0')}s`;
}

/**
 * What she is doing in the game right now, and the one way to override it.
 *
 * It reads the same things her own frame carries — the action in her hands,
 * how long it has been going, the last one she finished — so the dashboard
 * and she can never be looking at different games.
 */
export default function GamePanel() {
    const [now, setNow] = useState(null);
    const [busy, setBusy] = useState(false);
    const mounted = useRef(true);
    const toast = useToast();

    const read = useCallback(async () => {
        try {
            const next = await api.minecraftNow();
            if (mounted.current) setNow(next);
        } catch {
            // the engine is restarting or the page is stale; the next tick answers
        }
    }, []);

    useEffect(() => {
        mounted.current = true;
        read();
        const timer = setInterval(read, POLL_MS);
        return () => { mounted.current = false; clearInterval(timer); };
    }, [read]);

    const act = async (run, failure) => {
        setBusy(true);
        try {
            await run();
            await read();
        } catch (e) {
            toast.error(failure, e.message);
        } finally {
            if (mounted.current) setBusy(false);
        }
    };

    const playing = Boolean(now?.active);
    const doing = playing && Boolean(now?.doing);
    const state = !playing ? STATES.off : doing ? STATES.busy : STATES.idle;

    return (
        <Glass quiet className="mb-2.5 rounded-b3 p-4 sm:p-5">
            <div className="mb-3 flex flex-wrap items-center gap-3">
                <h2 className="mr-auto font-display text-[13px] font-semibold text-text">In the game</h2>
                {doing && (
                    <span className="tnum font-mono text-[11px] text-faint">{elapsed(now.elapsed)}</span>
                )}
                <Badge color={state.color} dot>{state.label}</Badge>
            </div>

            {!playing ? (
                <p className="text-[12px] leading-snug text-faint">
                    Turn Minecraft on and she connects to the server. Nothing here works until she does.
                </p>
            ) : (
                <>
                    <p className="break-words text-[13px] leading-snug text-text">
                        {doing ? now.doing : 'Her hands are free. She decides what to do next.'}
                    </p>

                    {doing && now.progress && (
                        <p className="mt-2.5 border-l border-line pl-3 text-[12px] italic leading-snug text-dim">
                            {now.progress}
                        </p>
                    )}

                    {now.last && (
                        <p className="mt-2.5 break-words text-[12px] leading-snug text-faint">
                            Last finished: {now.last}
                        </p>
                    )}

                    <div className="mt-4 flex flex-wrap gap-2">
                        {doing && (
                            <Button
                                size="md"
                                variant="danger"
                                loading={busy}
                                onClick={() => act(() => api.stopMinecraft(), 'She did not stop')}
                            >
                                <Square size={13} /> Stop
                            </Button>
                        )}
                        <Button
                            size="md"
                            variant="ghost"
                            onClick={() => act(() => api.askMinecraft(), 'She did not answer')}
                        >
                            <Hand size={13} /> Ask her what she is doing
                        </Button>
                    </div>
                </>
            )}
        </Glass>
    );
}
