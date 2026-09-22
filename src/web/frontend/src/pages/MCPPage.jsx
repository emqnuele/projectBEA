import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Boxes, ChevronRight, Globe, Lock, Puzzle, Shield, Terminal, ToggleLeft, ToggleRight } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { titleCase } from '../lib/format';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { Button, Segmented } from '../components/ui/controls';
import { Badge, EmptyState, Skeleton, Spinner } from '../components/ui/feedback';

/**
 * MCP / Tools workspace.
 *
 * Model Context Protocol is how Shura reaches tools she does not build herself —
 * external servers that expose capabilities through a standard wire format.
 *
 * The brain has no MCP-specific endpoint yet, so this page reads what it can from
 * /config and renders the framework it will plug into once that endpoint exists.
 * The cards are interactive now (expanded detail, connection-state indicators)
 * so the first real server connects to a ready surface, not a blank page.
 */

const VIEW = [
    { value: 'grid', label: 'Servers' },
    { value: 'tools', label: 'All tools' },
];

// a representative set of what an MCP server exposes, used as scaffolding
// until the real endpoint ships
const SCAFFOLD = [
    {
        id: 'filesystem',
        name: 'Filesystem',
        description: 'Read, write, and search the local filesystem.',
        status: 'disconnected',
        auth: 'local',
        tools: ['read_file', 'write_file', 'list_dir', 'glob', 'grep'],
    },
    {
        id: 'browser',
        name: 'Browser',
        description: 'Drive a real browser for the pages she cannot reach through search.',
        status: 'disconnected',
        auth: 'local',
        tools: ['navigate', 'snapshot', 'click', 'type', 'evaluate'],
    },
    {
        id: 'memory',
        name: 'Memory Store',
        description: 'Vector-backed recall she can query outside the sliding window.',
        status: 'disconnected',
        auth: 'token',
        tools: ['store', 'recall', 'forget', 'list_collections'],
    },
];

export default function MCPPage() {
    const [config, setConfig] = useState(null);
    const [expanded, setExpanded] = useState(null);
    const [view, setView] = useState('grid');
    const [loading, setLoading] = useState(false);
    const toast = useToast();

    const load = useCallback(async () => {
        try {
            const data = await api.config();
            setConfig(data);
        } catch (e) {
            toast.error('Could not read config', e.message);
        }
    }, [toast]);

    useEffect(() => { load(); }, [load]);

    // once the MCP endpoint ships, this is what it will connect to
    const connectServer = async (id) => {
        setLoading(true);
        try {
            // placeholder: api.mcpConnect(id) when the endpoint exists
            await new Promise((resolve) => setTimeout(resolve, 400));
            toast.info(`${titleCase(id)} — endpoint not yet implemented`);
        } catch (e) {
            toast.error('Could not connect', e.message);
        } finally {
            setLoading(false);
        }
    };

    const allTools = useMemo(() => {
        return SCAFFOLD.flatMap((s) => s.tools.map((t) => ({ server: s.name, tool: t, status: s.status })));
    }, []);

    if (config === null) {
        return (
            <div className="grid gap-2.5 lg:grid-cols-[240px_1fr]">
                <Skeleton className="h-full" />
                <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                    {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-40" />)}
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
                <Boxes size={15} className="text-faint" />
                <div className="mr-auto">
                    <h1 className="font-display text-[13px] font-semibold text-text">MCP & Tools</h1>
                    <p className="text-[11px] text-faint">
                        Model Context Protocol — the servers whose capabilities she can reach.
                    </p>
                </div>
                <Segmented value={view} onChange={setView} options={VIEW} size="sm" />
            </Glass>

            {/* config-derived mcp summary, when present */}
            {config.mcp_servers && config.mcp_servers.length > 0 ? (
                <Glass quiet className="rounded-b3 p-4">
                    <h2 className="mb-3 font-display text-[12px] font-semibold text-text">Configured in /config</h2>
                    <ul className="space-y-1">
                        {config.mcp_servers.map((s) => (
                            <li key={s.name} className="flex items-center gap-3 text-[12px] text-dim">
                                <Puzzle size={13} className="text-faint" />
                                <span className="font-mono text-text">{s.name}</span>
                                <span className="text-faint">—</span>
                                <span>{s.url || s.command || 'no endpoint'}</span>
                                <Badge color={s.enabled ? 'var(--flux-act)' : 'var(--flux-mute)'} dot className="ml-auto">
                                    {s.enabled ? 'enabled' : 'disabled'}
                                </Badge>
                            </li>
                        ))}
                    </ul>
                </Glass>
            ) : null}

            {view === 'grid' ? (
                <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                    {SCAFFOLD.map((server, index) => {
                        const isOpen = expanded === server.id;
                        return (
                            <motion.div
                                key={server.id}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: Math.min(index * 0.04, 0.3) }}
                            >
                                <Glass quiet className="flex h-full flex-col rounded-b3 p-4">
                                    <div className="flex items-start gap-3">
                                        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-b2 bg-[color:color-mix(in_oklab,var(--accent)_14%,transparent)] text-[color:var(--accent)]">
                                            <Globe size={17} />
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <p className="truncate font-display text-sm font-semibold text-text">{server.name}</p>
                                            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-faint">
                                                {server.auth === 'token' ? <Lock size={10} /> : <Shield size={10} />}
                                                {server.auth}
                                                <span className="mx-1">·</span>
                                                <span className="text-[color:var(--flux-mute)]">offline</span>
                                            </p>
                                        </div>
                                        <Badge color="var(--flux-mute)" dot className="shrink-0">disconnected</Badge>
                                    </div>

                                    <p className="mt-3 text-[12px] leading-relaxed text-dim">{server.description}</p>

                                    <button
                                        onClick={() => setExpanded(isOpen ? null : server.id)}
                                        className="mt-3 flex items-center gap-1 text-[11px] font-medium text-faint transition-colors hover:text-text"
                                    >
                                        <ChevronRight size={12} className={cn('transition-transform', isOpen && 'rotate-90')} />
                                        {server.tools.length} tools
                                    </button>

                                    <div className="mt-auto flex items-center gap-2 pt-3">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            loading={loading}
                                            onClick={() => connectServer(server.id)}
                                        >
                                            Connect
                                        </Button>
                                    </div>

                                    {isOpen && (
                                        <motion.ul
                                            initial={{ opacity: 0, height: 0 }}
                                            animate={{ opacity: 1, height: 'auto' }}
                                            className="mt-3 space-y-1 border-t border-line pt-3"
                                        >
                                            {server.tools.map((t) => (
                                                <li key={t} className="flex items-center gap-2 text-[11px] font-mono text-dim">
                                                    <Terminal size={10} className="text-faint" />
                                                    {t}
                                                </li>
                                            ))}
                                        </motion.ul>
                                    )}
                                </Glass>
                            </motion.div>
                        );
                    })}
                </div>
            ) : (
                <Glass quiet className="rounded-b3 p-4">
                    <h2 className="mb-3 font-display text-[12px] font-semibold text-text">All available tools</h2>
                    {allTools.length === 0 ? (
                        <EmptyState icon={Puzzle} title="No tools yet">Servers connect here once the endpoint ships.</EmptyState>
                    ) : (
                        <ul className="divide-y divide-[color:var(--line)]">
                            {allTools.map(({ server, tool, status }) => (
                                <li key={`${server}-${tool}`} className="flex items-center gap-3 py-2">
                                    <span className="w-28 shrink-0 truncate font-mono text-[10px] text-faint">{server}</span>
                                    <Terminal size={10} className="text-faint" />
                                    <span className="min-w-0 flex-1 font-mono text-[12px] text-dim">{tool}</span>
                                    <Badge color={status === 'connected' ? 'var(--flux-act)' : 'var(--flux-mute)'} dot className="shrink-0">
                                        {status}
                                    </Badge>
                                </li>
                            ))}
                        </ul>
                    )}
                </Glass>
            )}

            <Glass quiet className="rounded-b3 p-4">
                <h2 className="mb-1 font-display text-[12px] font-semibold text-text">Framework ready</h2>
                <p className="text-[12px] leading-relaxed text-dim">
                    The MCP wire protocol is not exposed by the brain yet. These cards are the surface it will
                    plug into — connection state, tool discovery, and per-server auth will render here the
                    moment <code className="font-mono text-text">/mcp</code> lands. Until then, tools the brain
                    builds herself (memory, web, chat) live in Abilities.
                </p>
            </Glass>
        </motion.div>
    );
}
