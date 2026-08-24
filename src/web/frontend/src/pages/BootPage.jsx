import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Check, Loader2, X } from 'lucide-react';
import { api } from '../api';
import { VERSION } from '../lib/nav';
import { cn } from '../lib/cn';
import { Glass } from '../components/glass/Glass';
import { Button } from '../components/ui/controls';
import { Magnetic, SplitText } from '../components/motion/effects';

const CHECKS = [
    { id: 'reachable', label: 'Brain' },
    { id: 'model', label: 'Model' },
    { id: 'voice', label: 'Voice' },
    { id: 'skills', label: 'Abilities' },
];

/**
 * The way in.
 *
 * This used to be a button that navigated. If the brain was not running you
 * landed on a dashboard where every request failed quietly. Now the door tells
 * you the state of the thing behind it before you walk through, and opens by
 * itself once everything answers.
 */
export default function BootPage() {
    const navigate = useNavigate();
    const [state, setState] = useState({ phase: 'checking', overview: null, error: null });
    const entered = useRef(false);

    const probe = useCallback(async () => {
        setState((prev) => ({ ...prev, phase: 'checking', error: null }));
        try {
            await api.health();
            const overview = await api.overview();
            setState({ phase: 'ready', overview, error: null });
        } catch (e) {
            setState({ phase: 'down', overview: null, error: e.message });
        }
    }, []);

    useEffect(() => { probe(); }, [probe]);

    // keep knocking while it is down, so starting the brain is enough
    useEffect(() => {
        if (state.phase !== 'down') return undefined;
        const timer = setInterval(probe, 4000);
        return () => clearInterval(timer);
    }, [state.phase, probe]);

    const enter = useCallback(() => {
        if (entered.current) return;
        entered.current = true;
        navigate('/dashboard');
    }, [navigate]);

    useEffect(() => {
        if (state.phase !== 'ready') return undefined;
        const timer = setTimeout(enter, 1400);
        return () => clearTimeout(timer);
    }, [state.phase, enter]);

    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Enter' && state.phase === 'ready') enter(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [state.phase, enter]);

    const overview = state.overview;
    const results = {
        reachable: state.phase === 'ready' ? 'ok' : state.phase === 'down' ? 'fail' : 'wait',
        model: overview ? (overview.engine.model ? 'ok' : 'fail') : state.phase === 'down' ? 'fail' : 'wait',
        voice: overview ? 'ok' : state.phase === 'down' ? 'fail' : 'wait',
        skills: overview ? (overview.skills.some((s) => s.enabled) ? 'ok' : 'fail') : state.phase === 'down' ? 'fail' : 'wait',
    };
    const detail = {
        reachable: state.phase === 'down' ? 'not answering' : 'answering',
        model: overview?.engine.model || '—',
        voice: overview?.engine.tts_provider || '—',
        skills: overview ? `${overview.skills.filter((s) => s.enabled).length} of ${overview.skills.length} on` : '—',
    };

    return (
        <div className="grid h-full place-items-center p-5">
            <Glass className="w-full max-w-md rounded-b4 p-8 sm:p-10">
                <motion.p
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}
                    className="font-mono text-[10px] uppercase tracking-[0.28em] text-faint"
                >
                    Control room {VERSION}
                </motion.p>

                <h1 className="mt-3 font-display text-5xl font-extrabold leading-none tracking-tight text-text">
                    <SplitText text="Bea" />
                </h1>

                <motion.p
                    initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.42, duration: 0.5 }}
                    className="mt-3 text-[13px] leading-relaxed text-dim"
                >
                    One consciousness across Discord, Telegram, Twitch and a Minecraft server.
                    This is where you watch her and tell her what today is for.
                </motion.p>

                <ul className="mt-7 space-y-px">
                    {CHECKS.map((check, index) => (
                        <motion.li
                            key={check.id}
                            initial={{ opacity: 0, x: -6 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.5 + index * 0.08 }}
                            className="flex items-center gap-3 border-b border-line py-2.5 last:border-0"
                        >
                            <StatusDot result={results[check.id]} />
                            <span className="text-[13px] font-medium text-text">{check.label}</span>
                            <span className="ml-auto truncate font-mono text-[11px] text-faint">
                                {detail[check.id]}
                            </span>
                        </motion.li>
                    ))}
                </ul>

                <div className="mt-7">
                    {state.phase === 'down' ? (
                        <div
                            className="rounded-b2 border p-3.5"
                            style={{
                                borderColor: 'color-mix(in srgb, var(--flux-err) 30%, transparent)',
                                background: 'color-mix(in srgb, var(--flux-err) 8%, transparent)',
                            }}
                        >
                            <p className="text-[13px] font-semibold" style={{ color: 'var(--flux-err)' }}>
                                The brain is not running
                            </p>
                            <p className="mt-1.5 text-[12px] leading-relaxed text-dim">
                                Start it and this screen lets you in on its own:
                            </p>
                            <code className="mt-2.5 block rounded-b1 border border-line bg-black/30 px-2.5 py-2 font-mono text-[11px] text-text">
                                uv run bea --web
                            </code>
                            <div className="mt-3 flex items-center gap-2">
                                <Button size="sm" variant="outline" onClick={probe}>Check again</Button>
                                <Button size="sm" variant="ghost" onClick={enter}>Go in anyway</Button>
                            </div>
                        </div>
                    ) : (
                        <Magnetic>
                            <Button
                                variant="primary"
                                size="lg"
                                onClick={enter}
                                loading={state.phase === 'checking'}
                                className="w-full"
                            >
                                {state.phase === 'checking' ? 'Waking the room' : 'Enter the control room'}
                                {state.phase === 'ready' && <ArrowRight size={15} />}
                            </Button>
                        </Magnetic>
                    )}
                </div>
            </Glass>
        </div>
    );
}

function StatusDot({ result }) {
    const shared = 'grid h-5 w-5 shrink-0 place-items-center rounded-full';
    if (result === 'wait') {
        return (
            <span className={cn(shared, 'text-faint')}>
                <Loader2 size={12} className="animate-spin" />
            </span>
        );
    }
    if (result === 'fail') {
        return (
            <span
                className={shared}
                style={{ color: 'var(--flux-err)', background: 'color-mix(in srgb, var(--flux-err) 14%, transparent)' }}
            >
                <X size={12} strokeWidth={3} />
            </span>
        );
    }
    return (
        <motion.span
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 500, damping: 24 }}
            className={shared}
            style={{ color: 'var(--flux-act)', background: 'color-mix(in srgb, var(--flux-act) 14%, transparent)' }}
        >
            <Check size={12} strokeWidth={3} />
        </motion.span>
    );
}
