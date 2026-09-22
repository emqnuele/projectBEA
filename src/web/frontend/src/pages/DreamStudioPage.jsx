import React, { useCallback, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    ChevronRight, Clock, Eye, Moon, Play, RefreshCw, Sparkles, Square, Sunrise, Terminal,
} from 'lucide-react';
import { api, API_BASE, request } from '../api';
import { cn } from '../lib/cn';
import { clockTime, relativeTime, titleCase } from '../lib/format';
import { useStore } from '../store';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { Button } from '../components/ui/controls';
import { Badge, EmptyState, Skeleton, Spinner } from '../components/ui/feedback';
import { AnimatedIcon, CountUp } from '../components/motion/effects';

const DREAM_STAGES = [
    { key: 'idle', label: 'Idle', icon: Square, color: 'var(--flux-mute)' },
    { key: 'entering', label: 'Entering', icon: Moon, color: 'var(--dream)' },
    { key: 'running', label: 'Dreaming', icon: Sparkles, color: 'var(--dream)' },
    { key: 'consolidating', label: 'Consolidating', icon: RefreshCw, color: 'var(--cognition)' },
    { key: 'waking', label: 'Waking', icon: Sunrise, color: 'var(--flux-act)' },
    { key: 'complete', label: 'Complete', icon: Eye, color: 'var(--flux-success)' },
];

export default function DreamStudioPage() {
    const status = useStore((s) => s.status);
    const overview = useStore((s) => s.overview);
    const toast = useToast();

    const [projection, setProjection] = useState(null);
    const [dreamEvents, setDreamEvents] = useState([]);
    const [snapshotObservations, setSnapshotObservations] = useState([]);
    const [stage, setStage] = useState('idle');
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [waking, setWaking] = useState(false);

    const isSleeping = Boolean(status?.is_sleeping);
    const dreamState = status?.dream_state || (isSleeping ? 'dreaming' : 'awake');

    const loadProjection = useCallback(async () => {
        try {
            const data = await request('/dream/projection');
            setProjection(data);
        } catch (e) {
            // projection may not be available
        }
    }, []);

    const loadDreamEvents = useCallback(async () => {
        try {
            const data = await request('/workspace/dream-events');
            setDreamEvents(data?.events || data || []);
        } catch (e) {
            // endpoint may not exist yet
        }
    }, []);

    const loadSnapshots = useCallback(async () => {
        try {
            const data = await request('/memory/snapshots');
            setSnapshotObservations(data?.observations || data || []);
        } catch {
            // snapshots may not be available
        }
    }, []);

    const loadAll = useCallback(async () => {
        setLoading(true);
        await Promise.allSettled([loadProjection(), loadDreamEvents(), loadSnapshots()]);
        setLoading(false);
    }, [loadProjection, loadDreamEvents, loadSnapshots]);

    useEffect(() => { loadAll(); }, [loadAll]);

    useEffect(() => {
        if (dreamState === 'dreaming') setStage('running');
        else if (dreamState === 'awake') setStage('idle');
    }, [dreamState]);

    const runDream = async () => {
        setRunning(true);
        setStage('entering');
        try {
            await api.dreamRun();
            toast.success('Dream pass initiated');
            setStage('running');
            const poll = setInterval(async () => {
                try {
                    const s = await api.status();
                    if (!s.is_sleeping) {
                        clearInterval(poll);
                        setStage('complete');
                        setRunning(false);
                        await loadAll();
                    }
                } catch {
                    clearInterval(poll);
                    setStage('idle');
                    setRunning(false);
                }
            }, 3000);
        } catch (e) {
            toast.error('Dream pass failed', e.message);
            setStage('idle');
            setRunning(false);
        }
    };

    const wakeUp = async () => {
        setWaking(true);
        setStage('waking');
        try {
            await api.dreamWake();
            toast.success('Wake command sent');
            setStage('idle');
        } catch (e) {
            toast.error('Could not wake her', e.message);
            setStage('running');
        } finally {
            setWaking(false);
        }
    };

    const currentStageIndex = DREAM_STAGES.findIndex((s) => s.key === stage);
    const activeStage = DREAM_STAGES[currentStageIndex] || DREAM_STAGES[0];

    return (
        <div className="flex h-full flex-col gap-2.5">
            <Glass quiet className="flex flex-wrap items-center gap-3 rounded-b3 px-4 py-3">
                <div className="mr-auto flex items-center gap-2.5">
                    <Moon size={15} className="text-faint" />
                    <div>
                        <h1 className="font-display text-[13px] font-semibold text-text">Dream Studio</h1>
                        <p className="text-[11px] text-faint">
                            Observe and guide the dream pass
                        </p>
                    </div>
                </div>
                <Badge color={isSleeping ? 'var(--dream)' : 'var(--flux-success)'} dot>
                    {isSleeping ? 'dreaming' : 'awake'}
                </Badge>
                <Button
                    size="sm"
                    variant="primary"
                    onClick={runDream}
                    disabled={running || isSleeping}
                    loading={running}
                >
                    <Sparkles size={13} /> Run Dream
                </Button>
                {isSleeping && (
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={wakeUp}
                        disabled={waking}
                        loading={waking}
                    >
                        <Sunrise size={13} /> Wake
                    </Button>
                )}
                <Button size="sm" variant="ghost" onClick={loadAll} disabled={loading}>
                    <RefreshCw size={13} /> Refresh
                </Button>
            </Glass>

            <div className="grid min-h-0 flex-1 gap-2.5 lg:grid-cols-3">
                <Glass quiet className="rounded-b3 p-4 lg:col-span-1">
                    <h3 className="mb-4 flex items-center gap-2 font-display text-[12px] font-semibold text-text">
                        <Clock size={13} className="text-faint" />
                        Lifecycle
                    </h3>
                    <ol className="space-y-1">
                        {DREAM_STAGES.map((s, i) => {
                            const isActive = i === currentStageIndex;
                            const isPast = i < currentStageIndex;
                            return (
                                <li key={s.key}>
                                    <div
                                        className={cn(
                                            'flex items-center gap-3 rounded-b2 px-3 py-2 transition-colors',
                                            isActive && 'bg-fill-2',
                                        )}
                                    >
                                        <span
                                            className={cn(
                                                'grid h-7 w-7 place-items-center rounded-full border',
                                                isActive && 'border-line-strong',
                                            )}
                                            style={{
                                                borderColor: isActive ? s.color : undefined,
                                                background: isActive ? `color-mix(in srgb, ${s.color} 12%, transparent)` : undefined,
                                            }}
                                        >
                                            <s.icon size={14} style={{ color: isActive ? s.color : 'var(--text-faint)' }} />
                                        </span>
                                        <span
                                            className={cn(
                                                'text-[12px]',
                                                isActive ? 'font-semibold text-text' : isPast ? 'text-dim' : 'text-faint',
                                            )}
                                        >
                                            {s.label}
                                        </span>
                                        {isActive && (
                                            <span className="ml-auto">
                                                <AnimatedIcon icon={s.icon} state="pulse" size={14} />
                                            </span>
                                        )}
                                    </div>
                                    {i < DREAM_STAGES.length - 1 && (
                                        <div className="ml-3.5 h-3 w-px bg-line" />
                                    )}
                                </li>
                            );
                        })}
                    </ol>

                    {projection && (
                        <div className="mt-4 border-t border-line pt-4">
                            <h4 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-faint">
                                Projection
                            </h4>
                            <dl className="space-y-1.5">
                                <DetailRow label="Mode" value={projection.mode || '—'} />
                                <DetailRow label="Depth" value={projection.depth || '—'} />
                                <DetailRow label="Cycles" value={projection.cycles ?? status?.dream_cycles ?? '—'} />
                            </dl>
                        </div>
                    )}
                </Glass>

                <Glass quiet className="flex flex-col rounded-b3 p-4 lg:col-span-2">
                    <div className="mb-4 flex items-center gap-2">
                        <Eye size={13} className="text-faint" />
                        <h3 className="font-display text-[12px] font-semibold text-text">
                            Snapshot Observations
                        </h3>
                        <span className="ml-auto font-mono text-[10px] text-faint">
                            {snapshotObservations.length} observations
                        </span>
                    </div>

                    {loading ? (
                        <div className="flex flex-1 items-center justify-center">
                            <Spinner size={20} />
                        </div>
                    ) : snapshotObservations.length === 0 ? (
                        <div className="flex flex-1 items-center justify-center">
                            <EmptyState icon={Eye} title="No observations yet">
                                Observations appear here as the dream pass runs.
                            </EmptyState>
                        </div>
                    ) : (
                        <div className="flex-1 space-y-2 overflow-y-auto pr-0.5">
                            <AnimatePresence initial={false}>
                                {snapshotObservations.slice(0, 30).map((obs, i) => (
                                    <motion.div
                                        key={obs.id || i}
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.2 }}
                                        className="rounded-b2 border border-line bg-fill p-3"
                                    >
                                        <div className="flex items-start gap-2">
                                            <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[color:var(--dream)]" />
                                            <p className="text-[12px] leading-snug text-dim">{obs.text || obs.observation || obs}</p>
                                        </div>
                                        {obs.timestamp && (
                                            <p className="mt-1.5 font-mono text-[10px] text-faint">
                                                {clockTime(obs.timestamp)}
                                            </p>
                                        )}
                                    </motion.div>
                                ))}
                            </AnimatePresence>
                        </div>
                    )}
                </Glass>

                <Glass quiet className="flex flex-col rounded-b3 p-4 lg:col-span-3">
                    <div className="mb-4 flex items-center gap-2">
                        <Terminal size={13} className="text-faint" />
                        <h3 className="font-display text-[12px] font-semibold text-text">
                            Event Replay
                        </h3>
                        <span className="ml-auto font-mono text-[10px] text-faint">
                            {dreamEvents.length} events
                        </span>
                    </div>

                    {loading ? (
                        <div className="flex flex-1 items-center justify-center">
                            <Spinner size={20} />
                        </div>
                    ) : dreamEvents.length === 0 ? (
                        <div className="flex flex-1 items-center justify-center">
                            <EmptyState icon={Terminal} title="No dream events">
                                Events from the dream pass will replay here.
                            </EmptyState>
                        </div>
                    ) : (
                        <div className="flex-1 space-y-1.5 overflow-y-auto pr-0.5">
                            {dreamEvents.slice(0, 50).map((event, i) => (
                                <div
                                    key={event.id || i}
                                    className="flex items-start gap-2.5 rounded-b2 border border-line bg-fill px-3 py-2"
                                >
                                    <span className="tnum shrink-0 pt-px font-mono text-[10px] text-faint">
                                        {clockTime(event.timestamp)}
                                    </span>
                                    <span
                                        className="w-12 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[9px] font-bold"
                                        style={{
                                            color: event.type === 'observation' ? 'var(--dream)' : 'var(--flux-act)',
                                            background: `color-mix(in srgb, ${event.type === 'observation' ? 'var(--dream)' : 'var(--flux-act)'} 13%, transparent)`,
                                        }}
                                    >
                                        {event.type || 'event'}
                                    </span>
                                    <span className="min-w-0 flex-1 text-[11.5px] leading-relaxed text-dim">
                                        {event.message || event.text || JSON.stringify(event)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </Glass>
            </div>
        </div>
    );
}

function DetailRow({ label, value }) {
    return (
        <div className="flex items-baseline gap-3">
            <dt className="shrink-0 text-[11px] text-faint">{label}</dt>
            <dd className="ml-auto min-w-0 truncate text-right text-[12px] text-dim">{String(value)}</dd>
        </div>
    );
}
