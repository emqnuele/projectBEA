import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, Circle, CircleDot, ListPlus, Sparkles } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { titleCase } from '../lib/format';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { Button } from '../components/ui/controls';
import { Badge, EmptyState, Skeleton } from '../components/ui/feedback';

const PRIORITY = {
    high: 'var(--flux-err)',
    normal: 'var(--flux-think)',
    low: 'var(--flux-mute)',
};
const PRIORITY_LABEL = { high: 'High', normal: 'Normal', low: 'Low' };
const PRIORITY_OPTIONS = ['high', 'normal', 'low'];

/**
 * Agent / task visibility: the ATLAS project layer made visible.
 */
export default function AgentsPage() {
    const [projects, setProjects] = useState(null);
    const [projectId, setProjectId] = useState(null);
    const [items, setItems] = useState(null);
    const [showForm, setShowForm] = useState(false);
    const toast = useToast();

    const [title, setTitle] = useState('');
    const [priority, setPriority] = useState('normal');
    const [description, setDescription] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const loadProjects = useCallback(async () => {
        try {
            const data = await api.atlasListProjects();
            setProjects(data);
            if (data.length > 0 && projectId === null) setProjectId(data[0].id);
        } catch (e) {
            setProjects([]);
            toast.error('Could not list projects', e.message);
        }
    }, [projectId, toast]);

    const loadItems = useCallback(async (id) => {
        if (id === null) return;
        setItems(null);
        try {
            setItems(await api.atlasListWorkItems(id));
        } catch (e) {
            setItems([]);
            toast.error('Could not load work items', e.message);
        }
    }, [toast]);

    useEffect(() => { loadProjects(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => { loadItems(projectId); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

    const activeProject = useMemo(
        () => projects?.find((p) => p.id === projectId) || null,
        [projects, projectId],
    );

    const stats = useMemo(() => {
        if (!items) return null;
        const open = items.filter((i) => i.status === 'todo' || i.status === 'doing').length;
        const done = items.filter((i) => i.status === 'done').length;
        const blocked = items.filter((i) => i.status === 'blocked').length;
        return { open, done, blocked, total: items.length };
    }, [items]);

    const resetForm = () => { setTitle(''); setPriority('normal'); setDescription(''); setShowForm(false); };

    const submit = async (event) => {
        event.preventDefault();
        const trimmed = title.trim();
        if (!trimmed) { toast.error('Give the work item a title'); return; }
        setSubmitting(true);
        try {
            await api.atlasCreateWorkItem(projectId, trimmed, { description, priority });
            toast.success(`Added "${trimmed}"`);
            await loadItems(projectId);
            resetForm();
        } catch (e) {
            toast.error('Could not create work item', e.message);
        } finally {
            setSubmitting(false);
        }
    };

    if (projects === null) {
        return (
            <div className="grid gap-2.5 lg:grid-cols-[240px_1fr]">
                <Skeleton className="h-full" />
                <div className="grid gap-2.5 sm:grid-cols-2">
                    {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
                </div>
            </div>
        );
    }

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex h-full flex-col gap-2.5 overflow-y-auto pr-0.5"
        >
            <Glass quiet className="flex flex-wrap items-center gap-3 rounded-b3 px-4 py-3">
                <Activity size={15} className="text-faint" />
                <div className="mr-auto">
                    <h1 className="font-display text-[13px] font-semibold text-text">Agent Tasks</h1>
                    <p className="text-[11px] text-faint">ATLAS projects and their work items.</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                    {projects.map((p) => {
                        const active = p.id === projectId;
                        return (
                            <button
                                key={p.id}
                                onClick={() => setProjectId(p.id)}
                                className={cn(
                                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
                                    active
                                        ? 'border-[color:color-mix(in_oklab,var(--accent)_30%,transparent)] bg-[color:color-mix(in_oklab,var(--accent)_12%,transparent)] text-text'
                                        : 'border-line text-faint hover:text-dim hover:bg-fill-2',
                                )}
                            >
                                {active ? <CircleDot size={11} /> : <Circle size={11} className="text-faint" />}
                                {p.name}
                            </button>
                        );
                    })}
                </div>
            </Glass>

            {activeProject && (
                <Glass quiet className="rounded-b3 p-4">
                    <div className="flex items-center gap-3">
                        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-b2" style={{ background: 'color-mix(in oklab, var(--accent) 14%, transparent)', color: 'var(--accent)' }}>
                            <Sparkles size={18} />
                        </span>
                        <div className="min-w-0 flex-1">
                            <h2 className="font-display text-[15px] font-bold text-text">{activeProject.name}</h2>
                            <p className="text-[12px] leading-relaxed text-dim">{activeProject.description || 'No description yet.'}</p>
                        </div>
                        {stats && (
                            <div className="flex gap-4 text-right">
                                <Stat label="Open" value={stats.open} />
                                <Stat label="Done" value={stats.done} />
                                <Stat label="Blocked" value={stats.blocked} />
                            </div>
                        )}
                    </div>
                </Glass>
            )}

            {items === null ? (
                <Skeleton className="h-64" />
            ) : items.length === 0 && !showForm ? (
                <EmptyState icon={CircleDot} title="No work items yet">
                    This project is empty.
                    <span className="mt-4 block">
                        <Button variant="primary" size="sm" onClick={() => setShowForm(true)}>
                            <ListPlus size={13} /> Add work item
                        </Button>
                    </span>
                </EmptyState>
            ) : (
                <>
                    {showForm && (
                        <form onSubmit={submit} className="rounded-b3 border border-line bg-raised p-4">
                            <h3 className="mb-3 font-display text-[12px] font-semibold text-text">New work item</h3>
                            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                                <input
                                    value={title}
                                    onChange={(e) => setTitle(e.target.value)}
                                    placeholder="What needs doing?"
                                    autoFocus
                                    className="min-w-0 rounded-b2 border border-line bg-fill px-3 py-2 text-[13px] text-text outline-none placeholder:text-faint"
                                />
                                <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-b2 border border-line bg-fill px-3 py-2 text-[12px] text-text outline-none">
                                    {PRIORITY_OPTIONS.map((p) => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
                                </select>
                            </div>
                            <textarea
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                placeholder="Optional detail."
                                rows={2}
                                className="mt-3 w-full rounded-b2 border border-line bg-fill px-3 py-2 text-[12px] text-text outline-none placeholder:text-faint"
                            />
                            <div className="mt-3 flex gap-2">
                                <Button type="submit" variant="primary" size="sm" loading={submitting}>Create</Button>
                                <Button variant="ghost" size="sm" onClick={resetForm}>Cancel</Button>
                            </div>
                        </form>
                    )}

                    <ul className="space-y-1.5">
                        {items.map((item, index) => (
                            <motion.li
                                key={item.id}
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: Math.min(index * 0.03, 0.2) }}
                                className="rounded-b2 border border-line bg-raised px-4 py-3"
                            >
                                <div className="flex items-start gap-3">
                                    <span className="mt-1 shrink-0">
                                        {item.status === 'done'
                                            ? <Circle size={14} className="text-[color:var(--flux-success)]" fill="currentColor" />
                                            : <CircleDot size={14} style={{ color: PRIORITY[item.priority] || 'var(--flux-mute)' }} />}
                                    </span>
                                    <div className="min-w-0 flex-1">
                                        <p className={cn('text-[13px] font-medium', item.status === 'done' ? 'text-faint line-through' : 'text-text')}>{item.title}</p>
                                        {item.description && <p className="mt-0.5 text-[12px] leading-relaxed text-dim">{item.description}</p>}
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                        <Badge style={{ color: PRIORITY[item.priority] || 'var(--flux-mute)', borderColor: `color-mix(in srgb, ${PRIORITY[item.priority] || 'var(--flux-mute)'} 34%, transparent)`, background: `color-mix(in srgb, ${PRIORITY[item.priority] || 'var(--flux-mute)'} 12%, transparent)` }}>
                                            {PRIORITY_LABEL[item.priority] || titleCase(item.priority)}
                                        </Badge>
                                        <Badge style={{ color: statusColor(item.status), borderColor: `color-mix(in srgb, ${statusColor(item.status)} 34%, transparent)`, background: `color-mix(in srgb, ${statusColor(item.status)} 12%, transparent)` }}>
                                            {titleCase(item.status)}
                                        </Badge>
                                    </div>
                                </div>
                            </motion.li>
                        ))}
                    </ul>
                </>
            )}

            {!showForm && items?.length > 0 && (
                <div className="flex justify-center pt-1">
                    <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
                        <ListPlus size={13} /> Add work item
                    </Button>
                </div>
            )}
        </motion.div>
    );
}

function Stat({ label, value }) {
    return (
        <div className="text-right">
            <p className="font-mono text-[9px] uppercase tracking-wider text-faint">{label}</p>
            <p className="font-display text-lg font-bold text-text">{value}</p>
        </div>
    );
}

function statusColor(status) {
    if (status === 'done') return 'var(--flux-success)';
    if (status === 'doing') return 'var(--flux-act)';
    if (status === 'blocked') return 'var(--flux-err)';
    return 'var(--flux-think)';
}
