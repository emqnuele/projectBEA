import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Hand, Send, Square } from 'lucide-react';
import { api } from '../../api';
import { Glass } from '../glass/Glass';
import { Button } from '../ui/controls';
import { TextInput } from '../ui/fields';
import { Badge } from '../ui/feedback';
import { useToast } from '../../state/ToastProvider';

const POLL_MS = 2000;

// the four answers to "do I need to do something about this", and nothing else.
// stuck is the only one that does, so stuck is the only one that alarms
const STATES = {
    running: { label: 'working', color: 'var(--flux-act)' },
    suspended: { label: 'paused', color: 'var(--flux-in)' },
    stuck: { label: 'stuck', color: 'var(--flux-err)' },
    done: { label: 'finished', color: 'var(--vital)' },
    idle: { label: 'idle', color: 'var(--text-dim)' },
    off: { label: 'not in the game', color: 'var(--text-dim)' },
};

function elapsed(seconds) {
    const whole = Math.max(0, Math.round(seconds || 0));
    if (whole < 60) return `${whole}s`;
    return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, '0')}s`;
}

/**
 * What her body is doing right now, and the two ways to override it.
 *
 * It reads the same three things her own context carries — the goal, how far
 * it has got, what it is thinking — so the dashboard and she can never be
 * looking at different bodies.
 */
export default function BodyPanel() {
    const [body, setBody] = useState(null);
    const [goal, setGoal] = useState('');
    const [busy, setBusy] = useState(false);
    const mounted = useRef(true);
    const toast = useToast();

    const read = useCallback(async () => {
        try {
            const next = await api.minecraftBody();
            if (mounted.current) setBody(next);
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

    const send = async () => {
        const text = goal.trim();
        if (!text) return;
        await act(() => api.setMinecraftGoal(text), 'She did not take the goal');
        if (mounted.current) setGoal('');
    };

    const state = STATES[body?.status] || STATES.off;
    const playing = Boolean(body?.active);
    const working = body?.status === 'running' || body?.status === 'suspended';
    const progress = body?.steps_budget
        ? Math.min(1, (body.steps || 0) / body.steps_budget)
        : 0;

    return (
        <Glass quiet className="mb-2.5 rounded-b3 p-4 sm:p-5">
            <div className="mb-3 flex flex-wrap items-center gap-3">
                <h2 className="mr-auto font-display text-[13px] font-semibold text-text">Her body</h2>
                {playing && working && (
                    <span className="tnum font-mono text-[11px] text-faint">
                        step {body.steps}/{body.steps_budget} · {elapsed(body.elapsed)}
                    </span>
                )}
                <Badge color={state.color} dot>{state.label}</Badge>
            </div>

            {!playing ? (
                <p className="text-[12px] leading-snug text-faint">
                    Turn Minecraft on and she connects to the server. Nothing here works until she does.
                </p>
            ) : (
                <>
                    <p className="text-[13px] leading-snug text-text">
                        {body.goal || 'No goal. She has not decided on anything, and neither have you.'}
                    </p>

                    {working && (
                        <div className="mt-2.5 h-[3px] overflow-hidden rounded-full bg-fill-2">
                            <motion.div
                                className="h-full rounded-full"
                                style={{ background: state.color }}
                                initial={false}
                                animate={{ width: `${progress * 100}%` }}
                                transition={{ type: 'spring', stiffness: 160, damping: 26 }}
                            />
                        </div>
                    )}

                    {body.thought && working && (
                        <p className="mt-2.5 border-l border-line pl-3 text-[12px] italic leading-snug text-dim">
                            {body.thought}
                        </p>
                    )}

                    {body.outcome && !working && (
                        <p className="mt-2.5 text-[12px] leading-snug text-faint">{body.outcome}</p>
                    )}

                    <div className="mt-4 flex flex-wrap gap-2">
                        <TextInput
                            value={goal}
                            onChange={(e) => setGoal(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
                            placeholder="Point her body at something"
                            className="min-w-[14rem] flex-1"
                            aria-label="Goal for her body"
                        />
                        <Button size="md" variant="outline" onClick={send} loading={busy} disabled={!goal.trim()}>
                            <Send size={13} /> Set goal
                        </Button>
                        {working ? (
                            <Button
                                size="md"
                                variant="danger"
                                onClick={() => act(() => api.stopMinecraftBody(), 'It did not stop')}
                            >
                                <Square size={13} /> Stop
                            </Button>
                        ) : (
                            <Button
                                size="md"
                                variant="ghost"
                                onClick={() => act(() => api.askMinecraft(), 'She did not answer')}
                            >
                                <Hand size={13} /> Ask her
                            </Button>
                        )}
                    </div>
                </>
            )}
        </Glass>
    );
}
