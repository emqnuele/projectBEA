import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
    ChevronRight, Clock, Cpu, FileText, FolderOpen, Hash, Send, Sparkles, Terminal,
} from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { clockTime, compact, duration, relativeTime, titleCase } from '../lib/format';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { Button, Segmented } from '../components/ui/controls';
import { Badge, EmptyState, Skeleton, Spinner } from '../components/ui/feedback';
import { CountUp } from '../components/motion/effects';

const SURFACES = [
    { value: 'project', label: 'Project' },
    { value: 'context', label: 'Context' },
    { value: 'sessions', label: 'Sessions' },
];

const COMMAND_HISTORY_KEY = 'shura.workspace.history';

export default function WorkspacePage() {
    const [surface, setSurface] = useState('project');
    const [overview, setOverview] = useState(null);
    const [loading, setLoading] = useState(true);
    const [command, setCommand] = useState('');
    const [history, setHistory] = useState([]);
    const [historyIndex, setHistoryIndex] = useState(-1);
    const [thinking, setThinking] = useState(false);

    const toast = useToast();
    const inputRef = useRef(null);

    const loadOverview = useCallback(async () => {
        try {
            const data = await api.overview();
            setOverview(data);
        } catch (e) {
            toast.error('Could not load workspace', e.message);
        } finally {
            setLoading(false);
        }
    }, [toast]);

    useEffect(() => { loadOverview(); }, [loadOverview]);

    useEffect(() => {
        try {
            const saved = localStorage.getItem(COMMAND_HISTORY_KEY);
            if (saved) setHistory(JSON.parse(saved));
        } catch {}
    }, []);

    const saveHistory = useCallback((cmd) => {
        if (!cmd.trim()) return;
        setHistory((prev) => {
            const next = [cmd, ...prev.filter((c) => c !== cmd)].slice(0, 50);
            localStorage.setItem(COMMAND_HISTORY_KEY, JSON.stringify(next));
            return next;
        });
    }, []);

    const executeCommand = async () => {
        const cmd = command.trim();
        if (!cmd || thinking) return;

        setCommand('');
        setHistoryIndex(-1);
        saveHistory(cmd);
        setThinking(true);

        try {
            const lower = cmd.toLowerCase();
            if (lower.startsWith('chat ')) {
                const message = cmd.slice(5);
                const result = await api.chat(message);
                toast.success('Message sent');
            } else if (lower === 'status') {
                const status = await api.status();
                toast.success(`Status: ${status.loop_phase || 'idle'}`);
            } else if (lower === 'dream') {
                await api.dreamRun();
                toast.success('Dream pass initiated');
            } else if (lower === 'wake') {
                await api.dreamWake();
                toast.success('Wake command sent');
            } else if (lower === 'save') {
                const result = await api.saveMemory();
                toast.success(result?.status === 'success' ? 'Memory saved' : 'Nothing to save');
            } else if (lower.startsWith('directive ')) {
                await api.setDirective(cmd.slice(10));
                toast.success('Directive updated');
            } else {
                toast.error('Unknown command', `Try: chat, status, dream, wake, save, directive`);
            }
            await loadOverview();
        } catch (e) {
            toast.error('Command failed', e.message);
        } finally {
            setThinking(false);
        }
    };

    const onKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            executeCommand();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (history.length === 0) return;
            const next = Math.min(historyIndex + 1, history.length - 1);
            setHistoryIndex(next);
            setCommand(history[next]);
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex <= 0) {
                setHistoryIndex(-1);
                setCommand('');
            } else {
                const next = historyIndex - 1;
                setHistoryIndex(next);
                setCommand(history[next]);
            }
        }
    };

    if (loading) {
        return (
            <div className="grid h-full gap-2.5">
                <Skeleton className="h-14" />
                <div className="grid flex-1 gap-2.5 lg:grid-cols-3">
                    <Skeleton className="lg:col-span-2" />
                    <Skeleton />
                </div>
            </div>
        );
    }

    if (!overview) {
        return (
            <Glass quiet className="grid h-full place-items-center rounded-b3">
                <EmptyState icon={FolderOpen} title="No workspace data">
                    The brain returned nothing. It may be starting up.
                </EmptyState>
            </Glass>
        );
    }

    const { plan, skills, memory, engine, session, context } = overview;

    return (
        <div className="flex h-full flex-col gap-2.5">
            <Glass quiet className="flex flex-wrap items-center gap-3 rounded-b3 px-4 py-3">
                <div className="mr-auto flex items-center gap-2.5">
                    <FolderOpen size={15} className="text-faint" />
                    <div>
                        <h1 className="font-display text-[13px] font-semibold text-text">Workspace</h1>
                        <p className="text-[11px] text-faint">
                            Active project and current session
                        </p>
                    </div>
                </div>
                <Segmented value={surface} onChange={setSurface} options={SURFACES} size="sm" />
            </Glass>

            <div className="grid min-h-0 flex-1 gap-2.5 lg:grid-cols-3">
                <div className="flex min-h-0 flex-col gap-2.5 lg:col-span-2">
                    {surface === 'project' && (
                        <ProjectPanel plan={plan} overview={overview} />
                    )}
                    {surface === 'context' && (
                        <ContextPanel context={context} />
                    )}
                    {surface === 'sessions' && (
                        <SessionsPanel session={session} />
                    )}

                    <Glass className="rounded-b3 p-4">
                        <div className="mb-3 flex items-center gap-2">
                            <Terminal size={14} className="text-faint" />
                            <h3 className="font-display text-[12px] font-semibold text-text">Command</h3>
                            <span className="font-mono text-[10px] text-faint">↑↓ history</span>
                        </div>
                        <div className="flex items-center gap-2 rounded-b2 border border-line bg-sunk px-3 py-2">
                            <ChevronRight size={14} className="shrink-0 text-accent" />
                            <input
                                ref={inputRef}
                                value={command}
                                onChange={(e) => setCommand(e.target.value)}
                                onKeyDown={onKeyDown}
                                placeholder="chat hello · status · dream · wake · directive save the world"
                                aria-label="Workspace command"
                                className="bare min-w-0 flex-1 bg-transparent font-mono text-[13px] text-text outline-none placeholder:text-faint"
                            />
                            <Button
                                size="sm"
                                variant="primary"
                                onClick={executeCommand}
                                disabled={!command.trim() || thinking}
                                loading={thinking}
                            >
                                <Send size={13} />
                            </Button>
                        </div>
                    </Glass>
                </div>

                <div className="flex min-h-0 flex-col gap-2.5">
                    <Glass quiet className="rounded-b3 p-4">
                        <h3 className="mb-3 flex items-center gap-2 font-display text-[12px] font-semibold text-text">
                            <Clock size={13} className="text-faint" />
                            Session
                        </h3>
                        <dl className="space-y-2">
                            <DetailRow label="ID" value={session.session_id?.slice(0, 8) || '—'} mono />
                            <DetailRow label="Messages" value={session.message_count ?? 0} />
                            <DetailRow label="Started" value={session.started_at ? relativeTime(session.started_at) : '—'} />
                        </dl>
                    </Glass>

                    <Glass quiet className="rounded-b3 p-4">
                        <h3 className="mb-3 flex items-center gap-2 font-display text-[12px] font-semibold text-text">
                            <Cpu size={13} className="text-faint" />
                            Engine
                        </h3>
                        <dl className="space-y-2">
                            <DetailRow label="Model" value={engine.model || '—'} mono />
                            <DetailRow label="Provider" value={engine.llm_provider || '—'} />
                            <DetailRow label="TTS" value={engine.tts_provider || '—'} />
                        </dl>
                    </Glass>

                    <Glass quiet className="rounded-b3 p-4">
                        <h3 className="mb-3 flex items-center gap-2 font-display text-[12px] font-semibold text-text">
                            <Sparkles size={13} className="text-faint" />
                            Skills
                        </h3>
                        <p className="font-display text-2xl font-bold text-text">
                            <CountUp value={skills.filter((s) => s.enabled).length} />
                            <span className="ml-1 font-sans text-xs font-medium text-faint">
                                / {skills.length}
                            </span>
                        </p>
                        <div className="mt-3 flex flex-wrap gap-1.5">
                            {skills.filter((s) => s.active).slice(0, 4).map((skill) => (
                                <Badge key={skill.name} color="var(--flux-act)">
                                    {titleCase(skill.name)}
                                </Badge>
                            ))}
                        </div>
                    </Glass>
                </div>
            </div>
        </div>
    );
}

function ProjectPanel({ plan, overview }) {
    const progress = plan.total ? plan.closed / plan.total : 0;

    return (
        <Glass quiet className="flex-1 rounded-b3 p-5">
            <div className="flex items-start gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-b2 bg-accent-soft text-accent">
                    <FileText size={18} />
                </span>
                <div className="min-w-0 flex-1">
                    <p className="font-mono text-[10px] uppercase tracking-widest text-faint">Current directive</p>
                    <p className="font-display text-lg font-bold text-text">
                        {plan.directive || 'No directive set'}
                    </p>
                    <p className="mt-1 text-[12px] text-dim">
                        {plan.closed} of {plan.total} objectives closed
                    </p>
                </div>
            </div>

            {plan.objectives?.length > 0 && (
                <ul className="mt-4 space-y-1.5 border-t border-line pt-3">
                    {plan.objectives.slice(0, 5).map((obj) => (
                        <li key={obj.id} className="flex items-center gap-2.5">
                            <span
                                className={cn('h-1.5 w-1.5 shrink-0 rounded-full', obj.status === 'doing' && 'animate-[shura-pulse_1.8s_ease-in-out_infinite]')}
                                style={{ background: obj.status === 'done' ? 'var(--flux-success)' : obj.status === 'doing' ? 'var(--vital)' : 'var(--text-faint)' }}
                            />
                            <span className={cn('truncate text-xs', obj.status === 'done' ? 'text-faint line-through' : 'text-dim')}>
                                {obj.text}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </Glass>
    );
}

function ContextPanel({ context }) {
    const pct = context?.enabled && context.max_tokens
        ? Math.min(1, context.total_tokens / context.max_tokens)
        : 0;

    return (
        <Glass quiet className="flex-1 rounded-b3 p-5">
            <h3 className="mb-3 font-display text-[13px] font-semibold text-text">Context Window</h3>
            {context?.enabled ? (
                <div>
                    <p className="font-display text-2xl font-bold text-text">
                        {Math.round(pct * 100)}%
                    </p>
                    <p className="mt-1 font-mono text-[11px] text-faint">
                        {compact(context.total_tokens)} of {compact(context.max_tokens)} tokens
                    </p>
                    <p className="mt-2 text-[12px] text-dim">
                        {context.handoff_running
                            ? 'Handing off to the next window…'
                            : context.swaps
                                ? `Handed off ${context.swaps}×`
                                : 'Filling up. The handoff starts at the trigger.'}
                    </p>
                </div>
            ) : (
                <p className="text-[12px] text-faint">The mind is not running.</p>
            )}
        </Glass>
    );
}

function SessionsPanel({ session }) {
    return (
        <Glass quiet className="flex-1 rounded-b3 p-5">
            <h3 className="mb-3 font-display text-[13px] font-semibold text-text">Current Session</h3>
            <dl className="space-y-2">
                <DetailRow label="ID" value={session.session_id || '—'} mono />
                <DetailRow label="Messages" value={session.message_count ?? 0} />
                <DetailRow label="Started" value={session.started_at ? relativeTime(session.started_at) : '—'} />
            </dl>
        </Glass>
    );
}

function DetailRow({ label, value, mono }) {
    return (
        <div className="flex items-baseline gap-3">
            <dt className="shrink-0 text-[11px] text-faint">{label}</dt>
            <dd className={cn('ml-auto min-w-0 truncate text-right text-[12px]', mono ? 'font-mono text-dim' : 'text-dim')}>
                {String(value)}
            </dd>
        </div>
    );
}
