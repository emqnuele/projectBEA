import React, { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Brain, Download, Pause, Play, Search, Terminal, X } from 'lucide-react';
import { cn, fluxOf } from '../lib/cn';
import { clockTime, compact } from '../lib/format';
import { useBrain } from '../state/BrainProvider';
import { useToast } from '../state/ToastProvider';
import { AttentionFlux } from '../components/AttentionFlux';
import { Glass } from '../components/glass/Glass';
import { Button, IconButton } from '../components/ui/controls';
import { EmptyState } from '../components/ui/feedback';
import { CountUp } from '../components/motion/effects';

const FILTERS = [
    { id: 'input', label: 'Perceptions', color: 'var(--flux-in)', match: (e) => e.category === 'input' && e.source !== 'attention' },
    { id: 'thought', label: 'Thoughts', color: 'var(--flux-think)', match: (e) => e.category === 'thought' },
    { id: 'output', label: 'Speech', color: 'var(--flux-out)', match: (e) => e.category === 'output' },
    { id: 'skill', label: 'Actions', color: 'var(--flux-act)', match: (e) => e.category === 'skill' },
    { id: 'error', label: 'Errors', color: 'var(--flux-err)', match: (e) => e.category === 'error' },
    { id: 'cost', label: 'Cost', color: 'var(--flux-cost)', match: (e) => e.source === 'cost' },
    { id: 'attention', label: 'Attention', color: 'var(--flux-mute)', match: (e) => e.source === 'attention' },
];

const DEFAULT_OFF = ['attention'];

export default function ActivityPage() {
    const { events, streaming } = useBrain();
    const toast = useToast();

    const [off, setOff] = useState(DEFAULT_OFF);
    const [query, setQuery] = useState('');
    const [paused, setPaused] = useState(false);
    const [frozen, setFrozen] = useState(null);

    const live = useMemo(() => {
        const active = FILTERS.filter((f) => !off.includes(f.id));
        const needle = query.trim().toLowerCase();
        return events.filter((event) => {
            if (!active.some((f) => f.match(event))) return false;
            if (!needle) return true;
            return event.message?.toLowerCase().includes(needle)
                || event.source?.toLowerCase().includes(needle);
        });
    }, [events, off, query]);

    // freezing takes a copy once, instead of writing to a ref on every render
    useEffect(() => { setFrozen(paused ? live : null); }, [paused]); // eslint-disable-line react-hooks/exhaustive-deps

    const shown = paused && frozen ? frozen : live;

    const errors = useMemo(() => events.filter((e) => e.category === 'error').length, [events]);
    const cost = useMemo(() => events.find((e) => e.source === 'cost'), [events]);

    const exportLog = () => {
        const text = [...shown].reverse()
            .map((e) => `${clockTime(e.timestamp)}\t${fluxOf(e).label}\t${e.source}\t${e.message}`)
            .join('\n');
        navigator.clipboard?.writeText(text)
            .then(() => toast.success(`${shown.length} lines copied`))
            .catch(() => toast.error('Could not copy the log'));
    };

    return (
        <div className="flex h-full flex-col gap-2.5">
            <div className="grid shrink-0 gap-2.5 lg:grid-cols-[1fr_auto]">
                <Glass quiet className="rounded-b3 p-4">
                    <div className="mb-3 flex items-center gap-2.5">
                        <Brain size={14} className="text-faint" />
                        <h2 className="font-display text-[13px] font-semibold text-text">Attention gate</h2>
                        <p className="truncate text-[11px] text-faint">
                            Every perception, and the verdict she gave it
                        </p>
                    </div>
                    <AttentionFlux count={96} size="lg" />
                </Glass>

                <Glass quiet className="grid grid-cols-3 gap-3 rounded-b3 p-4 lg:w-64 lg:grid-cols-1">
                    <Vital label="Events" value={<CountUp value={events.length} />} />
                    <Vital
                        label="Errors"
                        value={<CountUp value={errors} />}
                        color={errors ? 'var(--flux-err)' : undefined}
                    />
                    <Vital
                        label="Session"
                        value={cost ? `${compact(cost.metadata.session_tokens)} tok` : '—'}
                    />
                </Glass>
            </div>

            <Glass quiet className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-b3">
                <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5">
                    <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-faint">
                        <Terminal size={12} />
                        {streaming ? 'live' : 'polling'}
                    </span>

                    <span className="mx-1 h-4 w-px bg-[color:var(--line)]" />

                    <div className="flex flex-wrap gap-1">
                        {FILTERS.map((filter) => {
                            const on = !off.includes(filter.id);
                            return (
                                <button
                                    key={filter.id}
                                    onClick={() => setOff((prev) =>
                                        prev.includes(filter.id) ? prev.filter((id) => id !== filter.id) : [...prev, filter.id])}
                                    aria-pressed={on}
                                    className={cn(
                                        'flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors',
                                        on ? 'text-text' : 'border-line text-faint',
                                    )}
                                    style={on ? {
                                        borderColor: `color-mix(in srgb, ${filter.color} 40%, transparent)`,
                                        background: `color-mix(in srgb, ${filter.color} 12%, transparent)`,
                                    } : undefined}
                                >
                                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: on ? filter.color : 'var(--flux-mute)' }} />
                                    {filter.label}
                                </button>
                            );
                        })}
                    </div>

                    <div className="ml-auto flex items-center gap-1.5">
                        <label className="relative">
                            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-faint" />
                            <input
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Filter"
                                aria-label="Filter the log"
                                className="w-28 rounded-b1 border border-line bg-white/[0.03] py-1 pl-7 pr-6 text-[11px]
                                           text-text outline-none transition-all placeholder:text-faint
                                           focus:w-44 focus:border-line-strong"
                            />
                            {query && (
                                <button
                                    onClick={() => setQuery('')}
                                    aria-label="Clear filter"
                                    className="absolute right-1.5 top-1/2 -translate-y-1/2 text-faint hover:text-text"
                                >
                                    <X size={11} />
                                </button>
                            )}
                        </label>
                        <IconButton
                            label={paused ? 'Resume the feed' : 'Freeze the feed'}
                            size="sm"
                            onClick={() => setPaused((p) => !p)}
                            variant={paused ? 'vital' : 'ghost'}
                        >
                            {paused ? <Play size={12} /> : <Pause size={12} />}
                        </IconButton>
                        <IconButton label="Copy this log" size="sm" onClick={exportLog}>
                            <Download size={12} />
                        </IconButton>
                    </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto">
                    {shown.length === 0 ? (
                        <EmptyState icon={Terminal} title={query ? 'Nothing matches that' : 'Nothing yet'}>
                            {query
                                ? 'Try a different word, or turn a filter back on.'
                                : 'Events land here the moment anything reaches her.'}
                            {query && (
                                <span className="mt-4 block">
                                    <Button size="sm" variant="outline" onClick={() => { setQuery(''); setOff(DEFAULT_OFF); }}>
                                        Reset filters
                                    </Button>
                                </span>
                            )}
                        </EmptyState>
                    ) : (
                        <AnimatePresence initial={false}>
                            {shown.map((event) => <EventRow key={event.id} event={event} />)}
                        </AnimatePresence>
                    )}
                </div>

                <div className="flex items-center justify-between border-t border-line px-3 py-2 font-mono text-[10px] text-faint">
                    <span>{shown.length} shown of {events.length}</span>
                    {paused && <span style={{ color: 'var(--vital)' }}>frozen — new events are still arriving</span>}
                </div>
            </Glass>
        </div>
    );
}

function EventRow({ event }) {
    const [open, setOpen] = useState(false);
    const flux = fluxOf(event);
    const metadata = Object.entries(event.metadata || {});

    return (
        <motion.div
            layout="position"
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            className="border-b border-line last:border-0"
        >
            <button
                onClick={() => metadata.length && setOpen((v) => !v)}
                className={cn(
                    'flex w-full items-start gap-3 px-3 py-2 text-left transition-colors hover:bg-white/[0.03]',
                    !metadata.length && 'cursor-default',
                )}
            >
                <span className="tnum shrink-0 pt-px font-mono text-[10px] text-faint">
                    {clockTime(event.timestamp)}
                </span>
                <span
                    className="w-12 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[9px] font-bold"
                    style={{ color: flux.color, background: `color-mix(in srgb, ${flux.color} 13%, transparent)` }}
                >
                    {flux.label}
                </span>
                <span className="min-w-0 flex-1 break-words font-mono text-[11.5px] leading-relaxed text-dim">
                    {event.message}
                </span>
                {metadata.length > 0 && (
                    <span className="shrink-0 font-mono text-[9px] text-faint">{metadata.length} fields</span>
                )}
            </button>

            <AnimatePresence>
                {open && (
                    <motion.dl
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden bg-black/25 px-3 pb-2.5 pl-[7.5rem]"
                    >
                        {metadata.map(([key, value]) => (
                            <div key={key} className="flex gap-3 border-b border-line py-1 last:border-0">
                                <dt className="w-28 shrink-0 font-mono text-[10px] text-faint">{key}</dt>
                                <dd className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[10.5px] text-dim">
                                    {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                                </dd>
                            </div>
                        ))}
                    </motion.dl>
                )}
            </AnimatePresence>
        </motion.div>
    );
}

function Vital({ label, value, color }) {
    return (
        <div>
            <p className="font-mono text-[9px] uppercase tracking-wider text-faint">{label}</p>
            <p className="font-display text-lg font-bold leading-tight" style={{ color: color || 'var(--text)' }}>
                {value}
            </p>
        </div>
    );
}
