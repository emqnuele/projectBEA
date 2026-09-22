import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
    Activity, Brain, Cpu, Heart, Moon, Radio, Shield, Sparkles, Wifi, WifiOff, Zap,
} from 'lucide-react';
import { api } from '../api';
import { useStore } from '../store';
import { Glass } from '../components/glass/Glass';
import { Badge, EmptyState, Skeleton, Spinner } from '../components/ui/feedback';
import { AnimatedIcon, CountUp, ProgressRing } from '../components/motion/effects';
import { compact, duration, relativeTime, titleCase } from '../lib/format';
import { cn } from '../lib/cn';

export default function OverviewPage() {
    const { connection, streaming, events } = useStore();
    const [overview, setOverview] = useState(null);
    const [status, setStatus] = useState(null);
    const [persona, setPersona] = useState(null);

    useEffect(() => {
        api.overview().then(setOverview).catch(() => {});
        api.status().then(setStatus).catch(() => {});
        api.persona().then(setPersona).catch(() => {});
    }, []);

    const isSleeping = Boolean(status?.is_sleeping);
    const isSpeaking = Boolean(status?.is_speaking);
    const uptime = status?.uptime;
    const dreamState = status?.dream_state || (isSleeping ? 'dreaming' : 'awake');
    const loopPhase = status?.loop_phase || 'idle';
    const milestone = overview?.plan?.directive || 'No active directive';
    const enabledSkills = overview?.skills?.filter((s) => s.enabled) || [];
    const activeSkills = overview?.skills?.filter((s) => s.active) || [];
    const statusColor = isSleeping ? 'var(--dream)' : 'var(--vital)';

    const health = useMemo(() => {
        if (!status) return { ok: false, label: 'Unknown' };
        const checks = [
            connection === 'online',
            Boolean(status.model_loaded),
            Boolean(status.llm_provider),
        ];
        const passed = checks.filter(Boolean).length;
        if (passed === checks.length) return { ok: true, label: 'Nominal' };
        if (passed >= 2) return { ok: true, label: 'Degraded' };
        return { ok: false, label: 'Critical' };
    }, [status, connection]);

    const recentEvents = useMemo(
        () => events.filter((e) => Date.now() / 1000 - (e.timestamp || 0) < 3600).length,
        [events],
    );

    const planProgress = useMemo(() => {
        const total = overview?.plan?.total || 0;
        const closed = overview?.plan?.closed || 0;
        return total > 0 ? closed / total : 0;
    }, [overview?.plan]);

    if (!status && connection === 'offline') {
        return (
            <Glass quiet className="grid h-full place-items-center rounded-b3">
                <EmptyState icon={WifiOff} title="The brain is not running">
                    Start it with <code className="font-mono text-text">uv run shura --web</code> and this
                    dashboard fills itself in.
                </EmptyState>
            </Glass>
        );
    }

    return (
        <div className="h-full overflow-y-auto pb-2 pr-0.5">
            <div className="grid auto-rows-min grid-cols-1 gap-2.5 md:grid-cols-6 xl:grid-cols-12">

                {/* --- SHURA embodiment placeholder --- */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.32 }}
                    className="md:col-span-6 xl:col-span-5 xl:row-span-2"
                >
                    <Glass quiet className="h-full rounded-b3 p-5">
                        <div className="flex h-full flex-col">
                            <div className="flex items-start gap-3">
                                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-b2 bg-accent-soft text-accent">
                                    <AnimatedIcon
                                        icon={isSleeping ? Moon : isSpeaking ? Radio : Zap}
                                        state={isSpeaking ? 'pulse' : isSleeping ? 'breathe' : 'breathe'}
                                        size={19}
                                    />
                                </span>
                                <div className="min-w-0 flex-1">
                                    <p className="font-mono text-[10px] uppercase tracking-widest text-faint">
                                        Embodiment
                                    </p>
                                    <h2 className="font-display text-2xl font-bold leading-tight text-text">
                                        {persona?.name || 'SHURA'}
                                    </h2>
                                </div>
                                <Badge color={statusColor} dot>
                                    {isSleeping ? 'dreaming' : 'awake'}
                                </Badge>
                            </div>

                            {/* Avatar placeholder */}
                            <div className="mt-5 flex flex-1 items-center justify-center">
                                <div className="relative">
                                    <div
                                        className={cn(
                                            'grid h-24 w-24 place-items-center rounded-full border-2 font-display text-3xl font-bold',
                                            isSleeping ? 'border-dream bg-dream-soft text-dream' : 'border-accent bg-accent-soft text-accent',
                                            isSpeaking && 'animate-[shura-glow_2s_ease-in-out_infinite]',
                                        )}
                                    >
                                        <AnimatedIcon
                                            icon={isSleeping ? Moon : Brain}
                                            state={isSleeping ? 'breathe' : 'pulse'}
                                            size={32}
                                        />
                                    </div>
                                    {streaming && (
                                        <span className="absolute -bottom-1 -right-1 h-4 w-4 rounded-full border-2 border-bg bg-flux-success" />
                                    )}
                                </div>
                            </div>

                            <div className="mt-auto grid grid-cols-2 gap-2 pt-5">
                                <MiniStat label="Phase" value={titleCase(loopPhase)} />
                                <MiniStat label="Uptime" value={duration(uptime)} />
                            </div>
                        </div>
                    </Glass>
                </motion.div>

                {/* --- Loop phase / status --- */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.32, delay: 0.05 }}
                    className="md:col-span-3 xl:col-span-4"
                >
                    <Glass quiet className="h-full rounded-b3 p-4">
                        <div className="mb-3 flex items-center gap-2.5">
                            <Activity size={14} className="text-faint" />
                            <h3 className="font-display text-[13px] font-semibold text-text">Loop Phase</h3>
                        </div>
                        <p className="font-display text-2xl font-bold text-text">{titleCase(loopPhase)}</p>
                        <p className="mt-2 text-[12px] leading-snug text-dim">
                            {isSleeping
                                ? 'Consolidating memory — the dream pass is running.'
                                : isSpeaking
                                    ? 'Audio is going out.'
                                : 'Waiting for input.'}
                        </p>
                        <div className="mt-3 flex items-center gap-2">
                            <span
                                className="h-2 w-2 rounded-full"
                                style={{ background: connection === 'online' ? 'var(--flux-success)' : 'var(--flux-err)' }}
                            />
                            <span className="font-mono text-[10px] uppercase tracking-wider text-faint">
                                {connection === 'online' ? (streaming ? 'live' : 'connected') : 'offline'}
                            </span>
                        </div>
                    </Glass>
                </motion.div>

                {/* --- Active milestone --- */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.32, delay: 0.1 }}
                    className="md:col-span-3 xl:col-span-3"
                >
                    <Glass quiet className="h-full rounded-b3 p-4">
                        <div className="mb-3 flex items-center gap-2.5">
                            <Sparkles size={14} className="text-faint" />
                            <h3 className="font-display text-[13px] font-semibold text-text">Milestone</h3>
                        </div>
                        <p className={cn('text-[13px] font-medium leading-snug', milestone && milestone !== 'No active directive' ? 'text-text' : 'text-faint')}>
                            {milestone}
                        </p>
                        {overview?.plan?.total > 0 && (
                            <div className="mt-3">
                                <ProgressRing value={planProgress} size={36} thickness={3}>
                                    <span className="tnum font-mono text-[9px] text-dim">
                                        {Math.round(planProgress * 100)}%
                                    </span>
                                </ProgressRing>
                                <p className="mt-1 font-mono text-[10px] text-faint">
                                    {overview.plan.closed} of {overview.plan.total} closed
                                </p>
                            </div>
                        )}
                    </Glass>
                </motion.div>

                {/* --- Recent events --- */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.32, delay: 0.15 }}
                    className="md:col-span-3 xl:col-span-4"
                >
                    <Glass quiet className="h-full rounded-b3 p-4">
                        <div className="mb-3 flex items-center gap-2.5">
                            <Radio size={14} className="text-faint" />
                            <h3 className="font-display text-[13px] font-semibold text-text">Recent Events</h3>
                        </div>
                        <p className="font-display text-3xl font-bold leading-none text-text">
                            <CountUp value={recentEvents} />
                            <span className="ml-1.5 font-sans text-xs font-medium text-faint">/ hour</span>
                        </p>
                        <p className="mt-2 text-[11px] leading-snug text-dim">
                            {events.length} total in the live feed.
                        </p>
                    </Glass>
                </motion.div>

                {/* --- System health --- */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.32, delay: 0.2 }}
                    className="md:col-span-3 xl:col-span-3"
                >
                    <Glass quiet className="h-full rounded-b3 p-4">
                        <div className="mb-3 flex items-center gap-2.5">
                            <Shield size={14} className="text-faint" />
                            <h3 className="font-display text-[13px] font-semibold text-text">Health</h3>
                        </div>
                        <div className="flex items-center gap-2.5">
                            <span
                                className={cn('h-3 w-3 rounded-full', health.ok ? 'animate-[shura-pulse_2s_ease-in-out_infinite]' : '')}
                                style={{ background: health.ok ? 'var(--flux-success)' : 'var(--flux-err)' }}
                            />
                            <span className="font-display text-lg font-bold text-text">{health.label}</span>
                        </div>
                        <dl className="mt-3 space-y-1.5">
                            <HealthRow label="LLM" ok={Boolean(status?.llm_provider)} />
                            <HealthRow label="Model" ok={Boolean(status?.model_loaded)} />
                            <HealthRow label="Provider" ok={Boolean(status?.provider)} />
                        </dl>
                    </Glass>
                </motion.div>

                {/* --- Dream state --- */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.32, delay: 0.25 }}
                    className="md:col-span-6 xl:col-span-5"
                >
                    <Glass quiet className="h-full rounded-b3 p-4">
                        <div className="mb-3 flex items-center gap-2.5">
                            <Moon size={14} className="text-faint" />
                            <h3 className="font-display text-[13px] font-semibold text-text">Dream State</h3>
                        </div>
                        <div className="flex items-center gap-3">
                            <span
                                className={cn(
                                    'grid h-10 w-10 place-items-center rounded-b2',
                                    isSleeping ? 'bg-dream-soft text-dream' : 'bg-fill-2 text-dim',
                                )}
                            >
                                <AnimatedIcon
                                    icon={isSleeping ? Moon : Heart}
                                    state={isSleeping ? 'breathe' : 'idle'}
                                    size={20}
                                />
                            </span>
                            <div>
                                <p className="font-display text-lg font-bold text-text">
                                    {isSleeping ? 'Dreaming' : 'Awake'}
                                </p>
                                <p className="text-[12px] text-dim">
                                    {isSleeping
                                        ? 'Memory consolidation in progress.'
                                        : 'The dream pass consolidates memory while she sleeps.'}
                                </p>
                            </div>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2">
                            <MiniStat label="Dream cycles" value={status?.dream_cycles ?? '—'} />
                            <MiniStat label="Last dream" value={status?.last_dream ? relativeTime(status.last_dream) : '—'} />
                        </div>
                    </Glass>
                </motion.div>

                {/* --- Connection status --- */}
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.32, delay: 0.3 }}
                    className="md:col-span-6 xl:col-span-12"
                >
                    <Glass quiet className="rounded-b3 p-4">
                        <div className="flex flex-wrap items-center gap-4">
                            <div className="flex items-center gap-2.5">
                                {connection === 'online' ? (
                                    <Wifi size={14} className="text-flux-success" />
                                ) : (
                                    <WifiOff size={14} className="text-flux-err" />
                                )}
                                <h3 className="font-display text-[13px] font-semibold text-text">Connection</h3>
                            </div>
                            <Badge color={connection === 'online' ? 'var(--flux-success)' : 'var(--flux-err)'} dot>
                                {connection === 'online' ? (streaming ? 'live' : 'connected') : 'offline'}
                            </Badge>
                            <span className="text-[12px] text-dim">
                                {streaming
                                    ? 'Receiving events over Server-Sent Events.'
                                    : connection === 'offline'
                                        ? 'The brain is not answering. Start it with uv run shura --web.'
                                        : 'Falling back to polling.'}
                            </span>
                            {status?.session_id && (
                                <span className="ml-auto font-mono text-[10px] text-faint">
                                    session {status.session_id}
                                </span>
                            )}
                        </div>
                    </Glass>
                </motion.div>
            </div>
        </div>
    );
}

function MiniStat({ label, value }) {
    return (
        <div className="rounded-b2 border border-line bg-fill px-2.5 py-2">
            <p className="truncate font-mono text-[9px] uppercase tracking-wider text-faint">{label}</p>
            <p className="tnum mt-0.5 truncate font-display text-sm font-semibold text-text">{value}</p>
        </div>
    );
}

function HealthRow({ label, ok }) {
    return (
        <div className="flex items-center gap-2">
            <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: ok ? 'var(--flux-success)' : 'var(--flux-err)' }}
            />
            <span className="text-[11px] text-faint">{label}</span>
            <span className="ml-auto font-mono text-[10px]" style={{ color: ok ? 'var(--flux-success)' : 'var(--flux-err)' }}>
                {ok ? 'ok' : 'fail'}
            </span>
        </div>
    );
}
