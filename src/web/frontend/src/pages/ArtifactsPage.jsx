import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { FileText, File, Filter, ListPlus, Package, Plus, Search } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { clockTime, titleCase } from '../lib/format';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { Button, Segmented } from '../components/ui/controls';
import { Badge, EmptyState, Skeleton } from '../components/ui/feedback';

const TYPES = [
    { value: 'all', label: 'All' },
    { value: 'note', label: 'Notes' },
    { value: 'document', label: 'Docs' },
    { value: 'code', label: 'Code' },
    { value: 'config', label: 'Config' },
];

const TYPE_ICON = {
    note: FileText,
    document: File,
    code: FileText,
    config: FileText,
};

/**
 * Artifacts workspace: durable outputs the brain produces.
 *
 * An artifact is anything worth keeping beyond the turn that made it — a
 * decision record, a piece of code, a config snapshot. They live under a
 * project and are searchable by type.
 */
export default function ArtifactsPage() {
    const [projects, setProjects] = useState(null);
    const [projectId, setProjectId] = useState(null);
    const [artifacts, setArtifacts] = useState(null);
    const [typeFilter, setTypeFilter] = useState('all');
    const [query, setQuery] = useState('');
    const [showForm, setShowForm] = useState(false);
    const toast = useToast();

    // --- create form ---
    const [name, setName] = useState('');
    const [content, setContent] = useState('');
    const [type, setType] = useState('note');
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

    const loadArtifacts = useCallback(async (id) => {
        if (id === null) return;
        setArtifacts(null);
        try {
            setArtifacts(await api.atlasListArtifacts(id));
        } catch (e) {
            setArtifacts([]);
            toast.error('Could not load artifacts', e.message);
        }
    }, [toast]);

    useEffect(() => { loadProjects(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => { loadArtifacts(projectId); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

    const filtered = useMemo(() => {
        if (!artifacts) return [];
        const needle = query.trim().toLowerCase();
        return artifacts.filter((a) => {
            if (typeFilter !== 'all' && a.type !== typeFilter) return false;
            if (!needle) return true;
            return a.name?.toLowerCase().includes(needle);
        });
    }, [artifacts, typeFilter, query]);

    const resetForm = () => { setName(''); setContent(''); setType('note'); setShowForm(false); };

    const submit = async (event) => {
        event.preventDefault();
        const trimmed = name.trim();
        if (!trimmed) { toast.error('Give the artifact a name'); return; }
        if (!content.trim()) { toast.error('An artifact needs content'); return; }
        setSubmitting(true);
        try {
            await api.atlasCreateArtifact(projectId, trimmed, content, { type });
            toast.success(`Saved "${trimmed}"`);
            await loadArtifacts(projectId);
            resetForm();
        } catch (e) {
            toast.error('Could not create artifact', e.message);
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
                <Package size={15} className="text-faint" />
                <div className="mr-auto">
                    <h1 className="font-display text-[13px] font-semibold text-text">Artifacts</h1>
                    <p className="text-[11px] text-faint">
                        Durable outputs — decisions, code, configs, notes.
                    </p>
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
                                {p.name}
                            </button>
                        );
                    })}
                </div>
            </Glass>

            {/* --- controls --- */}
            <div className="flex flex-wrap items-center gap-2">
                <Segmented value={typeFilter} onChange={setTypeFilter} options={TYPES} size="sm" />
                <label className="relative ml-auto">
                    <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-faint" />
                    <input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search artifacts"
                        className="w-40 rounded-b1 border border-line bg-fill py-1.5 pl-7 pr-3 text-[11px] text-text outline-none placeholder:text-faint"
                    />
                </label>
                <Button size="sm" variant="primary" onClick={() => setShowForm(true)}>
                    <Plus size={13} /> New artifact
                </Button>
            </div>

            {/* --- create form --- */}
            {showForm && (
                <form onSubmit={submit} className="rounded-b3 border border-line bg-raised p-4">
                    <h3 className="mb-3 font-display text-[12px] font-semibold text-text">New artifact</h3>
                    <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Name"
                            autoFocus
                            className="min-w-0 rounded-b2 border border-line bg-fill px-3 py-2 text-[13px] text-text outline-none placeholder:text-faint"
                        />
                        <select value={type} onChange={(e) => setType(e.target.value)} className="rounded-b2 border border-line bg-fill px-3 py-2 text-[12px] text-text outline-none">
                            {TYPES.filter((t) => t.value !== 'all').map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                    </div>
                    <textarea
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        placeholder="Content — code, config, prose, anything."
                        rows={4}
                        className="mt-3 w-full rounded-b2 border border-line bg-fill px-3 py-2 font-mono text-[12px] text-text outline-none placeholder:text-faint"
                    />
                    <div className="mt-3 flex gap-2">
                        <Button type="submit" variant="primary" size="sm" loading={submitting}>Save</Button>
                        <Button variant="ghost" size="sm" onClick={resetForm}>Cancel</Button>
                    </div>
                </form>
            )}

            {/* --- list --- */}
            {artifacts === null ? (
                <Skeleton className="h-64" />
            ) : filtered.length === 0 ? (
                <EmptyState icon={Package} title="No artifacts match">
                    {artifacts.length === 0
                        ? 'This project has no saved artifacts yet.'
                        : 'Try a different type or clear the search.'}
                </EmptyState>
            ) : (
                <ul className="space-y-1.5">
                    {filtered.map((artifact, index) => {
                        const Icon = TYPE_ICON[artifact.type] || FileText;
                        return (
                            <motion.li
                                key={artifact.id}
                                initial={{ opacity: 0, y: 8 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: Math.min(index * 0.03, 0.2) }}
                                className="rounded-b2 border border-line bg-raised px-4 py-3"
                            >
                                <div className="flex items-start gap-3">
                                    <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-b1 bg-[color:color-mix(in_oklab,var(--accent)_12%,transparent)] text-[color:var(--accent)]">
                                        <Icon size={15} />
                                    </span>
                                    <div className="min-w-0 flex-1">
                                        <p className="text-[13px] font-medium text-text">{artifact.name}</p>
                                        {artifact.content && (
                                            <pre className="mt-1 max-h-20 overflow-hidden rounded-b1 bg-sunk px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-dim">
                                                {artifact.content.slice(0, 200)}
                                            </pre>
                                        )}
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                        <Badge style={{ color: 'var(--flux-think)', borderColor: 'color-mix(in srgb, var(--flux-think) 34%, transparent)', background: 'color-mix(in srgb, var(--flux-think) 12%, transparent)' }}>
                                            {titleCase(artifact.type || 'note')}
                                        </Badge>
                                        {artifact.created_at && (
                                            <span className="font-mono text-[10px] text-faint">{clockTime(artifact.created_at)}</span>
                                        )}
                                    </div>
                                </div>
                            </motion.li>
                        );
                    })}
                </ul>
            )}
        </motion.div>
    );
}
