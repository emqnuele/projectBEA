import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, Check, Stethoscope, X } from 'lucide-react';
import { api } from '../../api';
import { cn } from '../../lib/cn';
import { useToast } from '../../state/ToastProvider';
import { Glass } from '../glass/Glass';
import { Button } from '../ui/controls';
import { Spinner } from '../ui/feedback';

const VERDICT = {
    ok: { colour: 'var(--flux-act)', icon: Check },
    warning: { colour: 'var(--flux-think)', icon: AlertTriangle },
    blocked: { colour: 'var(--flux-err)', icon: X },
};

const POLL_EVERY = 700;

/**
 * The same checks `bea --doctor` runs, for the people who never open a terminal.
 *
 * They are the ones who need it: the failure it diagnoses looks, from the
 * dashboard, like nothing at all — she is simply quiet. Findings are rendered
 * as they land rather than at the end, because the run takes the better part of
 * a minute and a screen that sits still for a minute reads as broken.
 */
export function DoctorPanel() {
    const [run, setRun] = useState(null);
    const toast = useToast();
    const polling = useRef(null);

    const running = run?.state === 'running';

    const load = useCallback(async () => {
        try {
            return setRun(await api.doctor());
        } catch {
            return undefined;
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    useEffect(() => {
        if (!running) return undefined;
        polling.current = setInterval(load, POLL_EVERY);
        return () => clearInterval(polling.current);
    }, [running, load]);

    const start = async () => {
        try {
            setRun(await api.runDoctor());
        } catch (e) {
            toast.error('The checks could not start', e.message);
        }
    };

    const findings = run?.findings || [];
    const verdict = run?.verdict;

    return (
        <Glass quiet className="rounded-b3 p-5">
            <header className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="font-mono text-[10px] uppercase tracking-widest text-faint">Diagnosis</p>
                    <h2 className="font-display text-[17px] font-bold leading-tight text-text">
                        Is everything working?
                    </h2>
                    <p className="mt-1 max-w-md text-[12px] leading-relaxed text-dim">
                        Keys, the mind, her voice, her ears, her memory, her body, OBS and the
                        dashboard — checked in the order they depend on each other, stopping at the
                        first thing that would stop her.
                    </p>
                </div>
                <Button variant={findings.length ? 'outline' : 'primary'} size="sm"
                        onClick={start} loading={running}>
                    <Stethoscope size={13} /> {findings.length ? 'Run again' : 'Run the checks'}
                </Button>
            </header>

            {verdict && !running && <Verdict verdict={verdict} />}

            <ol className="mt-4 space-y-1">
                <AnimatePresence initial={false}>
                    {findings.map((finding) => (
                        <motion.li
                            key={finding.title}
                            layout
                            initial={{ opacity: 0, x: -6 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ type: 'spring', stiffness: 480, damping: 34 }}
                        >
                            <Finding finding={finding} />
                        </motion.li>
                    ))}
                </AnimatePresence>

                {running && (
                    <li className="flex items-center gap-2.5 px-1 py-1.5 text-[12px] text-faint">
                        <Spinner size={12} />
                        {findings.length
                            ? `${findings.length} of ${run.total} checked…`
                            : 'Starting…'}
                        <span className="text-faint/70">
                            some of these call your providers, so give it a moment
                        </span>
                    </li>
                )}
            </ol>

            {!findings.length && !running && (
                <p className="mt-4 text-[12px] leading-relaxed text-faint">
                    Nothing has been checked yet. The run builds her voice, transcribes a line and
                    asks the mind a question, so it costs a few requests at your provider.
                </p>
            )}
        </Glass>
    );
}

function Verdict({ verdict }) {
    const tone = VERDICT[verdict.level] || VERDICT.warning;
    const Icon = tone.icon;

    return (
        <div
            className="mt-4 flex items-start gap-3 rounded-b2 border px-3.5 py-3"
            style={{
                borderColor: `color-mix(in srgb, ${tone.colour} 32%, transparent)`,
                background: `color-mix(in srgb, ${tone.colour} 9%, transparent)`,
            }}
        >
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full"
                  style={{ background: `color-mix(in srgb, ${tone.colour} 18%, transparent)`, color: tone.colour }}>
                <Icon size={12} strokeWidth={2.8} />
            </span>
            <div className="min-w-0">
                <p className="text-[13px] font-semibold text-text">{verdict.headline}</p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-dim">{verdict.detail}</p>
            </div>
        </div>
    );
}

function Finding({ finding }) {
    const colour = finding.ok
        ? 'var(--flux-act)'
        : finding.blocking ? 'var(--flux-err)' : 'var(--flux-think)';
    const Icon = finding.ok ? Check : finding.blocking ? X : AlertTriangle;

    return (
        <div className="rounded-b2 px-1 py-1.5 transition-colors hover:bg-fill">
            <div className="flex items-start gap-2.5">
                <span className="mt-[2px] shrink-0" style={{ color: colour }}>
                    <Icon size={13} strokeWidth={2.6} />
                </span>
                <div className="min-w-0 flex-1">
                    <p className="text-[12.5px] leading-snug">
                        <span className={cn('font-semibold', finding.ok ? 'text-text' : 'text-text')}>
                            {finding.title}
                        </span>
                        {finding.detail && <span className="ml-2 text-faint">{finding.detail}</span>}
                    </p>
                    {/* the fix is the whole point of a failed check, so it is never folded away */}
                    {!finding.ok && finding.fix && (
                        <pre className="mt-1.5 whitespace-pre-wrap rounded-b1 border border-line bg-fill px-2.5 py-2
                                        font-mono text-[11px] leading-relaxed text-dim">
                            {finding.fix}
                        </pre>
                    )}
                </div>
            </div>
        </div>
    );
}
