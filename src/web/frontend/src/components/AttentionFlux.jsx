import React, { useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { cn } from '../lib/cn';
import { useEventFeed } from '../state/BrainProvider';

const VERDICT = {
    react: { color: 'var(--flux-out)', height: 1, label: 'Woke her' },
    note: { color: 'var(--flux-in)', height: 0.55, label: 'Noted' },
    drop: { color: 'var(--flux-mute)', height: 0.24, label: 'Ignored' },
};

function verdictOf(event) {
    const reaction = event.metadata?.reaction;
    return VERDICT[reaction] || VERDICT.drop;
}

/**
 * The attention gate, watched live.
 *
 * Everything she can perceive arrives here and gets one of three verdicts. It is
 * the only part of the engine that decides what is worth a thought, and until
 * now it was a grey line of text in a log. Each tick is one perception; the tall
 * warm ones are the ones that woke her.
 */
export function AttentionFlux({ count = 56, size = 'md', className }) {
    const { events } = useEventFeed({ sources: ['attention'], limit: count });

    const { ticks, tally } = useMemo(() => {
        const recent = [...events].reverse();
        const counts = { react: 0, note: 0, drop: 0 };
        for (const event of events) {
            const reaction = event.metadata?.reaction;
            if (reaction in counts) counts[reaction] += 1;
            else counts.drop += 1;
        }
        return { ticks: recent, tally: counts };
    }, [events]);

    const total = tally.react + tally.note + tally.drop;
    const barHeight = size === 'lg' ? 92 : 54;

    return (
        <div className={cn('flex flex-col gap-3', className)}>
            <div
                className="relative flex items-end gap-[3px] overflow-hidden rounded-b2 border border-line bg-sunk px-3"
                style={{ height: barHeight + 20 }}
            >
                {ticks.length === 0 && (
                    <span className="absolute inset-0 grid place-items-center font-mono text-[10px] uppercase tracking-widest text-faint">
                        nothing has reached her yet
                    </span>
                )}
                <AnimatePresence initial={false}>
                    {ticks.map((event) => {
                        const verdict = verdictOf(event);
                        const woke = verdict === VERDICT.react;
                        return (
                            <motion.span
                                key={event.id}
                                layout
                                initial={{ opacity: 0, scaleY: 0.2 }}
                                animate={{ opacity: 1, scaleY: 1 }}
                                exit={{ opacity: 0 }}
                                transition={{ type: 'spring', stiffness: 460, damping: 34 }}
                                title={`${verdict.label} — ${event.message}`}
                                className="w-[3px] shrink-0 origin-bottom rounded-full"
                                style={{
                                    height: barHeight * verdict.height,
                                    background: verdict.color,
                                    boxShadow: woke ? `0 0 10px ${verdict.color}` : 'none',
                                    marginBottom: 10,
                                }}
                            />
                        );
                    })}
                </AnimatePresence>
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                {Object.entries(VERDICT).map(([key, verdict]) => (
                    <span key={key} className="flex items-center gap-1.5 text-[11px] text-dim">
                        <span className="h-2 w-2 rounded-full" style={{ background: verdict.color }} />
                        {verdict.label}
                        <span className="tnum font-mono text-faint">{tally[key]}</span>
                    </span>
                ))}
                {total > 0 && (
                    <span className="ml-auto tnum font-mono text-[11px] text-faint">
                        {Math.round((tally.react / total) * 100)}% woke her
                    </span>
                )}
            </div>
        </div>
    );
}
