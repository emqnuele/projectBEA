import React, { useEffect, useMemo, useState } from 'react';
import { FileWarning } from 'lucide-react';
import { api } from '../../api';
import { cn } from '../../lib/cn';
import { alignLines, countChanges } from '../../lib/diff';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/controls';
import { Spinner } from '../ui/feedback';

const TONE = {
    same: '',
    changed: 'var(--flux-think)',
    added: 'var(--flux-act)',
    removed: 'var(--flux-err)',
};

/**
 * The two versions of a prompt the merge could not settle, side by side.
 *
 * The decision is deliberately not phrased as "resolve a conflict": the person
 * reading this wrote a character, they did not open a pull request. What they
 * are being asked is which of two paragraphs she should be reading from
 * tonight, and the left column is the one she is using right now.
 */
export function PromptReview({ name, open, onClose, onResolve }) {
    const [review, setReview] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!open || !name) return undefined;
        let alive = true;
        setReview(null);
        api.review(name)
            .then((data) => { if (alive) setReview(data); })
            .catch(() => { if (alive) setReview({ mine: '', theirs: '', failed: true }); });
        return () => { alive = false; };
    }, [open, name]);

    const diff = useMemo(
        () => (review ? alignLines(review.mine, review.theirs) : null),
        [review],
    );

    const settle = (choice) => async () => {
        setBusy(true);
        try {
            await onResolve(name, choice);
            onClose();
        } finally {
            setBusy(false);
        }
    };

    const changes = diff ? countChanges(diff.rows) : 0;

    return (
        <Modal
            open={open}
            onClose={onClose}
            size="xl"
            title={name}
            description={
                diff
                    ? `${changes} line${changes === 1 ? '' : 's'} differ · she is running the version on the left`
                    : 'Loading both versions…'
            }
            footer={
                <>
                    <Button variant="ghost" onClick={onClose} disabled={busy}>Decide later</Button>
                    <Button variant="outline" onClick={settle('theirs')} loading={busy}>
                        Use the new version
                    </Button>
                    <Button variant="primary" onClick={settle('mine')} loading={busy}>
                        Keep mine
                    </Button>
                </>
            }
        >
            {!diff ? (
                <div className="grid h-64 place-items-center"><Spinner size={20} /></div>
            ) : (
                <div className="-mx-1">
                    <div className="sticky top-0 z-10 grid grid-cols-2 gap-px bg-line text-[10px] font-mono uppercase tracking-widest">
                        <span className="bg-bg-raised px-3 py-1.5 text-dim">Yours · in use</span>
                        <span className="bg-bg-raised px-3 py-1.5 text-dim">The new version</span>
                    </div>
                    <div className="max-h-[56vh] overflow-auto rounded-b-b2 border border-line border-t-0">
                        <table className="w-full border-collapse font-mono text-[11.5px] leading-[1.55]">
                            <tbody>
                                {diff.rows.map((row, index) => (
                                    <Row key={index} row={row} />
                                ))}
                            </tbody>
                        </table>
                    </div>
                    {diff.truncated && (
                        <p className="mt-2 text-[11px] text-faint">
                            These files are too long to line up properly, so they are shown
                            side by side instead.
                        </p>
                    )}
                </div>
            )}
        </Modal>
    );
}

function Row({ row }) {
    const colour = TONE[row.state];
    const tint = colour
        ? { background: `color-mix(in srgb, ${colour} 9%, transparent)` }
        : undefined;

    return (
        <tr style={tint}>
            <Cell number={row.leftNumber} text={row.left} muted={row.state === 'added'} colour={colour} />
            <Cell number={row.rightNumber} text={row.right} muted={row.state === 'removed'} colour={colour}
                className="border-l border-line" />
        </tr>
    );
}

function Cell({ number, text, muted, colour, className }) {
    return (
        <td className={cn('w-1/2 align-top', className)}>
            <div className="flex gap-2.5 px-2 py-[1px]">
                <span className="w-7 shrink-0 select-none text-right text-faint/70">{number ?? ''}</span>
                <span
                    className={cn('min-w-0 flex-1 whitespace-pre-wrap break-words', muted && 'opacity-25')}
                    style={colour && !muted ? { color: colour } : undefined}
                >
                    {/* a blank line still has to occupy one, or the two sides stop lining up */}
                    {text === '' ? ' ' : text}
                </span>
            </div>
        </td>
    );
}

/** The list that sends people into the diff above. */
export function ReviewList({ reviews, onOpen }) {
    if (!reviews.length) return null;

    return (
        <div className="mt-4 space-y-1.5">
            {reviews.map((review) => (
                <button
                    key={review.name}
                    onClick={() => onOpen(review.name)}
                    className="group flex w-full items-center gap-3 rounded-b2 border px-3 py-2.5 text-left transition-colors"
                    style={{
                        borderColor: 'color-mix(in srgb, var(--flux-think) 30%, transparent)',
                        background: 'color-mix(in srgb, var(--flux-think) 8%, transparent)',
                    }}
                >
                    <FileWarning size={15} className="shrink-0" style={{ color: 'var(--flux-think)' }} />
                    <span className="min-w-0 flex-1">
                        <span className="block truncate font-mono text-xs font-semibold text-text">
                            {review.name}
                        </span>
                        <span className="block truncate text-[11px] text-faint">
                            Your version is in use. Compare it with the new one.
                        </span>
                    </span>
                    <span className="shrink-0 text-[11px] font-semibold text-dim group-hover:text-text">
                        Compare
                    </span>
                </button>
            ))}
        </div>
    );
}
