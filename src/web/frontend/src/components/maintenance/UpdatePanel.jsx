import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
    AlertTriangle, ArrowDownToLine, Check, CheckCircle2, Minus, RefreshCw, RotateCw, X,
} from 'lucide-react';
import { cn } from '../../lib/cn';
import { useUpdate } from '../../state/UpdateProvider';
import { useToast } from '../../state/ToastProvider';
import { Glass } from '../glass/Glass';
import { Button } from '../ui/controls';
import { Badge, Spinner } from '../ui/feedback';
import { PromptReview, ReviewList } from './PromptReview';

const STEP_ICON = {
    pending: { icon: Minus, colour: 'var(--text-faint)' },
    running: { icon: null, colour: 'var(--flux-think)' },
    done: { icon: Check, colour: 'var(--flux-act)' },
    skipped: { icon: Minus, colour: 'var(--text-faint)' },
    failed: { icon: X, colour: 'var(--flux-err)' },
};

const PROMPT_TONE = {
    merged: 'var(--flux-act)',
    kept: 'var(--flux-act)',
    untouched: 'var(--text-faint)',
    conflict: 'var(--flux-think)',
    removed: 'var(--flux-think)',
};

/**
 * The one screen that answers "am I behind, and what happens if I click".
 *
 * It is a small state machine — current, available, running, finished — and the
 * reason each state gets its own body rather than a shared one with flags is
 * that they are answering different questions. A changelog is useless while the
 * thing is installing, and a progress bar is noise once it is done.
 */
export function UpdatePanel() {
    const { status, run, report, available, running, checking, reviews, refresh, start, resolve }
        = useUpdate();
    const toast = useToast();
    const [reviewing, setReviewing] = useState(null);

    const finished = run?.state === 'done' && report;

    const install = async () => {
        try {
            await start();
        } catch (e) {
            toast.error('The update could not start', e.message);
        }
    };

    return (
        <Glass quiet className="rounded-b3 p-5">
            <header className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="font-mono text-[10px] uppercase tracking-widest text-faint">Version</p>
                    <h2 className="font-display text-2xl font-bold leading-tight text-text">
                        {status?.version || '—'}
                    </h2>
                    <p className="mt-1 font-mono text-[11px] text-faint">
                        {status?.current ? `commit ${status.current}` : 'not a git checkout'}
                    </p>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                    {status?.supported && !running && (
                        <Button variant="ghost" size="sm" onClick={() => refresh(true)} loading={checking}>
                            <RefreshCw size={13} /> Check again
                        </Button>
                    )}
                    {available && !running && !finished && (
                        <Button variant="primary" size="sm" onClick={install}>
                            <ArrowDownToLine size={13} /> Install update
                        </Button>
                    )}
                </div>
            </header>

            <div className="mt-5">
                <AnimatePresence mode="wait">
                    {running || finished ? (
                        <Fade key="run"><RunBody run={run} report={report} /></Fade>
                    ) : !status?.supported ? (
                        <Fade key="unsupported"><Unsupported reason={status?.reason} /></Fade>
                    ) : available ? (
                        <Fade key="available"><WhatIsNew status={status} /></Fade>
                    ) : (
                        <Fade key="current"><UpToDate checkedAt={status?.checked_at} /></Fade>
                    )}
                </AnimatePresence>
            </div>

            {reviews.length > 0 && (
                <section className="mt-6 border-t border-line pt-5">
                    <h3 className="font-display text-[13px] font-semibold text-text">
                        {reviews.length} prompt{reviews.length === 1 ? '' : 's'} kept your version
                    </h3>
                    <p className="mt-1 text-[12px] leading-relaxed text-dim">
                        An update changed the same lines you had edited, so nothing was touched — she
                        is running exactly what you wrote. The new version is waiting beside it.
                    </p>
                    <ReviewList reviews={reviews} onOpen={setReviewing} />
                </section>
            )}

            <PromptReview
                name={reviewing}
                open={Boolean(reviewing)}
                onClose={() => setReviewing(null)}
                onResolve={async (name, choice) => {
                    await resolve(name, choice);
                    toast.success(
                        choice === 'mine' ? 'Your version stays' : 'The new version is in place',
                        name,
                    );
                }}
            />
        </Glass>
    );
}

function Fade({ children }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
        >
            {children}
        </motion.div>
    );
}

function UpToDate({ checkedAt }) {
    return (
        <div className="flex items-center gap-3">
            <span
                className="grid h-9 w-9 shrink-0 place-items-center rounded-b2"
                style={{ background: 'color-mix(in srgb, var(--flux-act) 14%, transparent)', color: 'var(--flux-act)' }}
            >
                <CheckCircle2 size={17} />
            </span>
            <div className="min-w-0">
                <p className="text-[13px] font-semibold text-text">She is up to date</p>
                <p className="text-[11px] text-faint">
                    {checkedAt ? `Checked ${new Date(checkedAt * 1000).toLocaleTimeString()}` : 'Never checked'}
                </p>
            </div>
        </div>
    );
}

function Unsupported({ reason }) {
    return (
        <div className="flex items-start gap-3">
            <span
                className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-b2"
                style={{ background: 'var(--fill-2)', color: 'var(--text-faint)' }}
            >
                <AlertTriangle size={16} />
            </span>
            <div className="min-w-0">
                <p className="text-[13px] font-semibold text-text">This install cannot update itself</p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-dim">
                    {reason || 'Updating from here is not available.'}
                </p>
            </div>
        </div>
    );
}

function WhatIsNew({ status }) {
    return (
        <div>
            <div className="flex items-center gap-2.5">
                <Badge color="var(--vital)" dot>
                    {status.behind} new commit{status.behind === 1 ? '' : 's'}
                </Badge>
                <span className="font-mono text-[11px] text-faint">→ {status.latest}</span>
            </div>

            <p className="mt-3 text-[12px] leading-relaxed text-dim">
                Your config, your memory and the prompts you have edited are backed up first and put
                back afterwards. Nothing you wrote is overwritten.
            </p>

            <ul className="mt-4 max-h-56 space-y-1 overflow-y-auto pr-1">
                {status.commits.map((commit) => (
                    <li key={commit.sha} className="flex gap-2.5 text-[12px] leading-relaxed">
                        <span className="shrink-0 font-mono text-[11px] text-faint">{commit.sha}</span>
                        <span className="min-w-0 flex-1 text-dim">{commit.subject}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

function RunBody({ run, report }) {
    const steps = run?.steps || [];
    const settled = steps.filter((s) => ['done', 'skipped', 'failed'].includes(s.status)).length;
    const progress = steps.length ? settled / steps.length : 0;
    const failedSteps = steps.filter((s) => s.status === 'failed');

    return (
        <div>
            <div className="h-[3px] overflow-hidden rounded-full bg-fill-2">
                <motion.div
                    className="h-full rounded-full"
                    style={{ background: 'var(--vital)' }}
                    animate={{ width: `${Math.round(progress * 100)}%` }}
                    transition={{ type: 'spring', stiffness: 180, damping: 30 }}
                />
            </div>

            <ol className="mt-4 space-y-2">
                {steps.map((step) => <StepRow key={step.id} step={step} />)}
            </ol>

            {report && (
                <div className="mt-5 border-t border-line pt-4">
                    <p className={cn('text-[13px] font-semibold',
                        report.ok ? 'text-text' : 'text-[color:var(--flux-err)]')}>
                        {report.headline}
                    </p>
                    {report.detail && (
                        <p className="mt-1 text-[12px] leading-relaxed text-dim">{report.detail}</p>
                    )}

                    {report.blocked_paths?.length > 0 && (
                        <ul className="mt-2 space-y-0.5">
                            {report.blocked_paths.map((path) => (
                                <li key={path} className="font-mono text-[11px] text-faint">{path}</li>
                            ))}
                        </ul>
                    )}

                    {report.prompts?.length > 0 && (
                        <ul className="mt-3 space-y-1.5">
                            {report.prompts.map((prompt) => (
                                <li key={prompt.path} className="flex items-baseline gap-2 text-[12px]">
                                    <span
                                        className="h-1.5 w-1.5 shrink-0 translate-y-[-1px] rounded-full"
                                        style={{ background: PROMPT_TONE[prompt.state] || 'var(--text-faint)' }}
                                    />
                                    <span className="font-mono text-[11px] font-semibold text-text">{prompt.name}</span>
                                    <span className="min-w-0 flex-1 text-faint">{prompt.detail}</span>
                                </li>
                            ))}
                        </ul>
                    )}

                    {failedSteps.length > 0 && (
                        <p className="mt-3 text-[12px] leading-relaxed"
                           style={{ color: 'var(--flux-think)' }}>
                            She is on the new version, but part of the rebuild did not run.
                            {' '}{failedSteps.map((s) => s.detail).join(' ')}
                        </p>
                    )}

                    {report.backup && (
                        <p className="mt-3 font-mono text-[11px] text-faint">
                            backup · data/.backups/{report.backup}
                        </p>
                    )}

                    {report.restart_required && <RestartNotice />}
                </div>
            )}
        </div>
    );
}

function StepRow({ step }) {
    const tone = STEP_ICON[step.status] || STEP_ICON.pending;
    const Icon = tone.icon;

    return (
        <li className="flex items-start gap-2.5">
            <span className="mt-[1px] grid h-4 w-4 shrink-0 place-items-center" style={{ color: tone.colour }}>
                {step.status === 'running' ? <Spinner size={12} /> : Icon && <Icon size={13} strokeWidth={2.6} />}
            </span>
            <span className="min-w-0 flex-1">
                <span className={cn('text-[12.5px] font-medium',
                    step.status === 'pending' ? 'text-faint' : 'text-text')}>
                    {step.label}
                </span>
                {step.detail && (
                    <span className="ml-2 text-[11px] text-faint">{step.detail}</span>
                )}
            </span>
        </li>
    );
}

/** She keeps running the code she was started with until somebody restarts her. */
function RestartNotice() {
    return (
        <div
            className="mt-4 flex items-start gap-2.5 rounded-b2 border px-3 py-2.5"
            style={{
                borderColor: 'color-mix(in srgb, var(--vital) 34%, transparent)',
                background: 'var(--vital-soft)',
            }}
        >
            <RotateCw size={14} className="mt-0.5 shrink-0" style={{ color: 'var(--vital)' }} />
            <p className="text-[12px] leading-relaxed text-dim">
                The new version is on disk. She is still running the old one until you restart her:
                {' '}<code className="font-mono text-text">uv run bea --web</code>
            </p>
        </div>
    );
}
