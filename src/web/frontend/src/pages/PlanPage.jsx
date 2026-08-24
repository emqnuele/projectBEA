import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, Reorder, useDragControls } from 'framer-motion';
import { Ban, Check, GripVertical, Play, Plus, RotateCcw, Trash2, Undo2 } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { useToast } from '../state/ToastProvider';
import { useDialog } from '../state/DialogProvider';
import { Glass } from '../components/glass/Glass';
import { Button, IconButton } from '../components/ui/controls';
import { EmptyState, Skeleton } from '../components/ui/feedback';
import { ProgressRing } from '../components/motion/effects';

const STATUS = {
    todo: { label: 'To do', color: 'var(--text-faint)' },
    doing: { label: 'Doing', color: 'var(--vital)' },
    done: { label: 'Done', color: 'var(--flux-act)' },
    dropped: { label: 'Dropped', color: 'var(--flux-mute)' },
};

export default function PlanPage() {
    const [plan, setPlan] = useState(null);
    const [directive, setDirective] = useState('');
    const [newObjective, setNewObjective] = useState('');
    const [order, setOrder] = useState([]);
    const [savingDirective, setSavingDirective] = useState(false);

    const dirty = useRef(false);
    const toast = useToast();
    const dialog = useDialog();

    const apply = useCallback((data) => {
        setPlan(data);
        setOrder(data.objectives || []);
        if (!dirty.current) setDirective(data.directive || '');
    }, []);

    const load = useCallback(async () => {
        try {
            apply(await api.plan());
        } catch (e) {
            setPlan({ directive: '', objectives: [] });
            toast.error('Could not load the plan', e.message);
        }
    }, [apply, toast]);

    // she closes objectives herself while the stream runs, so this stays a poll
    useEffect(() => {
        load();
        const timer = setInterval(load, 5000);
        return () => clearInterval(timer);
    }, [load]);

    const call = async (promise, failure) => {
        try {
            apply(await promise);
            return true;
        } catch (e) {
            toast.error(failure, e.message);
            return false;
        }
    };

    const saveDirective = async () => {
        if (!dirty.current) return;
        setSavingDirective(true);
        const ok = await call(api.setDirective(directive), 'The orders were not saved');
        setSavingDirective(false);
        // only forget the local edit once the server has it
        if (ok) { dirty.current = false; toast.success('Orders saved'); }
    };

    const addObjective = async () => {
        const text = newObjective.trim();
        if (!text) return;
        setNewObjective('');
        await call(api.addObjective(text), 'The objective was not added');
    };

    const setStatus = (id, status) =>
        call(api.updateObjective(id, { status }), 'That objective did not change');

    const editText = (id, text) =>
        call(api.updateObjective(id, { text }), 'The wording did not save');

    const remove = async (objective) => {
        const ok = await dialog.confirm({
            title: 'Remove this objective?',
            message: objective.text,
            confirmLabel: 'Remove',
            danger: true,
        });
        if (ok) await call(api.deleteObjective(objective.id), 'It could not be removed');
    };

    const commitOrder = async (next) => {
        setOrder(next);
        await call(api.reorderPlan(next.map((o) => o.id)), 'The new order did not stick');
    };

    const clearPlan = async () => {
        const ok = await dialog.confirm({
            title: 'Clear today',
            message: 'The orders and every objective go away. This starts a new stream from nothing.',
            confirmLabel: 'Clear it',
            danger: true,
        });
        if (!ok) return;
        dirty.current = false;
        setDirective('');
        if (await call(api.resetPlan(), 'The plan was not cleared')) toast.success('Plan cleared');
    };

    if (plan === null) {
        return (
            <div className="mx-auto w-full max-w-3xl space-y-3">
                <Skeleton className="h-28" />
                <Skeleton className="h-64" />
            </div>
        );
    }

    const objectives = order;
    const closed = objectives.filter((o) => o.status === 'done' || o.status === 'dropped').length;
    const progress = objectives.length ? closed / objectives.length : 0;

    return (
        <div className="h-full overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl space-y-2.5 pb-6">

                <Glass className="rounded-b3 p-5 sm:p-6">
                    <div className="mb-3 flex items-center gap-3">
                        <span className="font-mono text-[10px] uppercase tracking-widest text-faint">
                            Today, in her own context
                        </span>
                        {savingDirective && <span className="text-[10px] text-faint">saving…</span>}
                        <span className="ml-auto flex items-center gap-3">
                            {objectives.length > 0 && (
                                <ProgressRing value={progress} size={30} thickness={2.5} />
                            )}
                            <span className="tnum font-mono text-[11px] text-faint">
                                {closed}/{objectives.length} closed
                            </span>
                        </span>
                    </div>

                    <textarea
                        value={directive}
                        onChange={(e) => { dirty.current = true; setDirective(e.target.value); }}
                        onBlur={saveDirective}
                        rows={2}
                        placeholder="Today you're playing Minecraft on the survival server…"
                        aria-label="Today's orders"
                        className="bare w-full resize-none bg-transparent font-display text-2xl font-bold leading-snug
                                   tracking-tight text-text outline-none placeholder:text-faint sm:text-3xl"
                    />
                    <p className="mt-2 text-[11px] text-faint">
                        She reads this every single turn. It saves when you click away.
                    </p>
                </Glass>

                <Glass quiet className="rounded-b3 p-4 sm:p-5">
                    <div className="mb-3 flex items-center gap-3">
                        <h2 className="font-display text-[13px] font-semibold text-text">Objectives</h2>
                        <span className="h-px flex-1 bg-[color:var(--line)]" />
                        {(objectives.length > 0 || plan.directive) && (
                            <button
                                onClick={clearPlan}
                                className="flex items-center gap-1.5 text-[11px] text-faint transition-colors hover:text-text"
                            >
                                <RotateCcw size={11} /> Clear today
                            </button>
                        )}
                    </div>

                    {objectives.length === 0 ? (
                        <EmptyState icon={Check} title="Nothing on the list">
                            She will still react to whatever happens — she just will not set out to do anything.
                        </EmptyState>
                    ) : (
                        <Reorder.Group axis="y" values={objectives} onReorder={commitOrder} className="space-y-1">
                            <AnimatePresence initial={false}>
                                {objectives.map((objective) => (
                                    <ObjectiveRow
                                        key={objective.id}
                                        objective={objective}
                                        onStatus={setStatus}
                                        onEdit={editText}
                                        onRemove={remove}
                                    />
                                ))}
                            </AnimatePresence>
                        </Reorder.Group>
                    )}

                    <div className="mt-4 flex gap-2">
                        <input
                            value={newObjective}
                            onChange={(e) => setNewObjective(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && addObjective()}
                            placeholder="Build a base before dark"
                            aria-label="New objective"
                            className="min-w-0 flex-1 rounded-b2 border border-line bg-fill px-3 py-2
                                       text-[13px] text-text outline-none transition-colors
                                       placeholder:text-faint"
                        />
                        <Button variant="primary" onClick={addObjective} disabled={!newObjective.trim()}>
                            <Plus size={14} /> Add
                        </Button>
                    </div>
                </Glass>
            </div>
        </div>
    );
}

function ObjectiveRow({ objective, onStatus, onEdit, onRemove }) {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState(objective.text);
    const controls = useDragControls();
    const status = STATUS[objective.status] || STATUS.todo;
    const closed = objective.status === 'done' || objective.status === 'dropped';

    const commit = () => {
        setEditing(false);
        const text = draft.trim();
        if (text && text !== objective.text) onEdit(objective.id, text);
        else setDraft(objective.text);
    };

    return (
        <Reorder.Item
            value={objective}
            dragListener={false}
            dragControls={controls}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, height: 0 }}
            className="group flex items-start gap-2.5 rounded-b2 border border-transparent px-2 py-2
                       transition-colors hover:border-line hover:bg-fill"
        >
            <button
                onPointerDown={(e) => controls.start(e)}
                aria-label="Reorder"
                className="mt-0.5 cursor-grab touch-none text-faint opacity-0 transition-opacity
                           group-hover:opacity-100 active:cursor-grabbing"
            >
                <GripVertical size={13} />
            </button>

            <span
                className={cn(
                    'mt-0.5 w-[3px] self-stretch rounded-full',
                    objective.status === 'doing' && 'animate-[bea-pulse_1.8s_ease-in-out_infinite]',
                )}
                style={{ background: status.color }}
            />

            <div className="min-w-0 flex-1">
                {editing ? (
                    <input
                        autoFocus
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onBlur={commit}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') commit();
                            if (e.key === 'Escape') { setDraft(objective.text); setEditing(false); }
                        }}
                        className="w-full rounded-b1 border border-line-strong bg-fill-2 px-2 py-1 text-[13px] text-text outline-none"
                    />
                ) : (
                    <button
                        onClick={() => setEditing(true)}
                        className={cn(
                            'block w-full text-left text-[13px] leading-snug',
                            closed ? 'text-faint line-through' : 'text-text',
                        )}
                    >
                        {objective.text}
                    </button>
                )}
                {objective.detail && <p className="mt-0.5 text-[11px] text-faint">{objective.detail}</p>}
                {objective.outcome && (
                    <p className="mt-1 text-[11px] italic text-dim">“{objective.outcome}”</p>
                )}
            </div>

            <span
                className="mt-0.5 shrink-0 font-mono text-[9px] uppercase tracking-wider"
                style={{ color: status.color }}
            >
                {status.label}
            </span>

            <span className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                {objective.status === 'todo' && (
                    <IconButton label="Start it" size="sm" onClick={() => onStatus(objective.id, 'doing')}>
                        <Play size={12} />
                    </IconButton>
                )}
                {objective.status !== 'done' && (
                    <IconButton label="Mark done" size="sm" onClick={() => onStatus(objective.id, 'done')}>
                        <Check size={12} />
                    </IconButton>
                )}
                {closed ? (
                    <IconButton label="Reopen" size="sm" onClick={() => onStatus(objective.id, 'todo')}>
                        <Undo2 size={12} />
                    </IconButton>
                ) : (
                    <IconButton label="Drop it" size="sm" onClick={() => onStatus(objective.id, 'dropped')}>
                        <Ban size={12} />
                    </IconButton>
                )}
                <IconButton label="Remove" size="sm" onClick={() => onRemove(objective)}>
                    <Trash2 size={12} />
                </IconButton>
            </span>
        </Reorder.Item>
    );
}
