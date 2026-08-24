import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Trash2, RotateCcw, Check, Play, Ban, Undo2 } from 'lucide-react';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { useDialog } from '../context/DialogContext';
import { API_BASE } from '../api';

const STATUS_LABEL = { todo: 'To do', doing: 'Doing', done: 'Done', dropped: 'Dropped' };

// the rail down the left of a row is the status: empty, live, filled, struck
const RAIL = {
    todo: 'bg-zinc-200',
    doing: 'bg-zinc-900',
    done: 'bg-emerald-500',
    dropped: 'bg-zinc-300',
};

export default function StreamPlanPage() {
    const [plan, setPlan] = useState({ directive: '', objectives: [] });
    const [draft, setDraft] = useState('');
    const [newText, setNewText] = useState('');
    const [loading, setLoading] = useState(true);
    const dirty = useRef(false);
    const dialog = useDialog();

    const apply = (data) => {
        setPlan(data);
        if (!dirty.current) setDraft(data.directive || '');
    };

    const load = async () => {
        try {
            const res = await fetch(`${API_BASE}/plan`);
            if (res.ok) apply(await res.json());
        } catch (e) {
            console.error('Failed to load the plan', e);
        } finally {
            setLoading(false);
        }
    };

    // she closes objectives herself while the stream runs, so this stays a poll
    useEffect(() => {
        load();
        const interval = setInterval(load, 5000);
        return () => clearInterval(interval);
    }, []);

    const post = async (path, body, method = 'POST') => {
        try {
            const res = await fetch(`${API_BASE}${path}`, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: body ? JSON.stringify(body) : undefined,
            });
            if (res.ok) apply(await res.json());
        } catch (e) {
            console.error(`Request to ${path} failed`, e);
        }
    };

    const saveDirective = async () => {
        dirty.current = false;
        await post('/plan/directive', { text: draft });
    };

    const addObjective = async () => {
        const text = newText.trim();
        if (!text) return;
        setNewText('');
        await post('/plan/objectives', { text });
    };

    const setStatus = (id, status) => post(`/plan/objectives/${id}`, { status }, 'PATCH');
    const remove = (id) => post(`/plan/objectives/${id}`, null, 'DELETE');

    const resetPlan = async () => {
        const ok = await dialog.confirm(
            'Clear the headline and every objective. This starts a new stream from nothing.',
            'Clear the plan',
        );
        if (ok) {
            dirty.current = false;
            setDraft('');
            await post('/plan/reset');
        }
    };

    const objectives = plan.objectives || [];
    const closed = objectives.filter(o => o.status === 'done' || o.status === 'dropped').length;

    if (loading) return <div className="p-10 text-zinc-400">Loading the plan…</div>;

    return (
        <div className="h-full w-full overflow-y-auto bg-transparent text-zinc-900">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="max-w-3xl px-8 py-10"
            >
                <div className="flex items-baseline justify-between mb-6">
                    <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-widest">
                        Today's plan
                    </span>
                    {objectives.length > 0 && (
                        <span className="text-xs font-medium text-zinc-400 tabular-nums">
                            {closed}/{objectives.length} closed
                        </span>
                    )}
                </div>

                {/* the orders, at the size they deserve */}
                <textarea
                    value={draft}
                    onChange={(e) => { dirty.current = true; setDraft(e.target.value); }}
                    onBlur={saveDirective}
                    rows={2}
                    placeholder="Today you're playing Minecraft on the survival server…"
                    className="w-full resize-none bg-transparent text-3xl font-bold tracking-tight
                               leading-snug text-zinc-900 placeholder:text-zinc-300
                               focus:outline-none"
                />
                <p className="mt-2 text-xs text-zinc-400">
                    She reads this every turn. Click away to save.
                </p>

                <div className="flex items-center gap-4 mt-10 mb-4">
                    <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-widest">
                        Objectives
                    </span>
                    <div className="flex-1 h-px bg-zinc-200/70" />
                    {(objectives.length > 0 || plan.directive) && (
                        <button
                            onClick={resetPlan}
                            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-900 transition-colors cursor-pointer"
                        >
                            <RotateCcw size={12} />
                            Clear plan
                        </button>
                    )}
                </div>

                <div className="space-y-1.5">
                    <AnimatePresence initial={false}>
                        {objectives.map((o) => (
                            <motion.div
                                key={o.id}
                                layout
                                initial={{ opacity: 0, y: -6 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, height: 0 }}
                                className="group flex items-start gap-3 rounded-lg border border-transparent
                                           px-3 py-2.5 hover:border-zinc-200/70 hover:bg-zinc-50/60 transition-colors"
                            >
                                <span className={`mt-0.5 w-[3px] self-stretch rounded-full ${RAIL[o.status] || RAIL.todo}
                                                  ${o.status === 'doing' ? 'animate-pulse' : ''}`} />
                                <span className="mt-[3px] text-xs font-medium text-zinc-300 tabular-nums w-6 shrink-0">
                                    #{o.id}
                                </span>

                                <div className="flex-1 min-w-0">
                                    <div className={`text-sm ${o.status === 'done' || o.status === 'dropped'
                                        ? 'text-zinc-400 line-through' : 'text-zinc-900'}`}>
                                        {o.text}
                                    </div>
                                    {o.detail && <div className="text-xs text-zinc-400 mt-0.5">{o.detail}</div>}
                                    {o.outcome && (
                                        <div className="text-xs text-zinc-500 mt-1 italic">“{o.outcome}”</div>
                                    )}
                                </div>

                                <span className="mt-[3px] text-[10px] font-medium uppercase tracking-wider text-zinc-400 shrink-0">
                                    {STATUS_LABEL[o.status] || o.status}
                                </span>

                                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                    {o.status === 'todo' && (
                                        <RowAction label="Start it" onClick={() => setStatus(o.id, 'doing')}>
                                            <Play size={13} />
                                        </RowAction>
                                    )}
                                    {o.status !== 'done' && (
                                        <RowAction label="Mark done" onClick={() => setStatus(o.id, 'done')}>
                                            <Check size={13} />
                                        </RowAction>
                                    )}
                                    {o.status === 'todo' || o.status === 'doing' ? (
                                        <RowAction label="Drop it" onClick={() => setStatus(o.id, 'dropped')}>
                                            <Ban size={13} />
                                        </RowAction>
                                    ) : (
                                        <RowAction label="Reopen" onClick={() => setStatus(o.id, 'todo')}>
                                            <Undo2 size={13} />
                                        </RowAction>
                                    )}
                                    <RowAction label="Remove" onClick={() => remove(o.id)}>
                                        <Trash2 size={13} />
                                    </RowAction>
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                </div>

                {objectives.length === 0 && (
                    <p className="text-sm text-zinc-400 px-3 py-2">
                        Nothing on the list. She'll react to whatever happens, but she won't
                        set out to do anything.
                    </p>
                )}

                <div className="flex gap-2 mt-4">
                    <Input
                        value={newText}
                        onChange={(e) => setNewText(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && addObjective()}
                        placeholder="Build a base before dark"
                        className="bg-white border-zinc-200 text-zinc-900 focus-visible:ring-zinc-200"
                    />
                    <Button
                        onClick={addObjective}
                        disabled={!newText.trim()}
                        className="bg-black text-white hover:bg-zinc-800 shrink-0 cursor-pointer"
                    >
                        <Plus size={15} className="mr-1.5" />
                        Add
                    </Button>
                </div>
            </motion.div>
        </div>
    );
}

function RowAction({ label, onClick, children }) {
    return (
        <button
            onClick={onClick}
            title={label}
            aria-label={label}
            className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-900 hover:bg-zinc-150
                       focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-1
                       focus-visible:ring-zinc-300 transition-colors cursor-pointer"
        >
            {children}
        </button>
    );
}
