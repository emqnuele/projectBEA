import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Activity, AlertTriangle, Check, Clock, Cpu, Globe, HardDrive, Info, Network, RefreshCw, Shield, Wifi, WifiOff } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { compact, duration, titleCase } from '../lib/format';
import { useStore } from '../store';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { Button } from '../components/ui/controls';
import { Badge, Skeleton } from '../components/ui/feedback';

const VERDICT = {
    ok: { colour: 'var(--flux-success)', icon: Check, label: 'Healthy' },
    warning: { colour: 'var(--flux-think)', icon: AlertTriangle, label: 'Degraded' },
    blocked: { colour: 'var(--flux-err)', icon: AlertTriangle, label: 'Down' },
};

/**
 * System page: health, config, diagnostics.
 *
 * The same information the operator gets from `uv run bea --doctor` and the
 * terminal — surfaced so most people never have to open one.
 */
export default function SystemPage() {
    const [health, setHealth] = useState(null);
    const [config, setConfig] = useState(null);
    const [doctor, setDoctor] = useState(null);
    const [running, setRunning] = useState(false);
    const toast = useToast();
    const status = useStore((s) => s.status);
    const connection = useStore((s) => s.connection);

    const load = useCallback(async () => {
        try {
            const [h, c] = await Promise.all([api.health(), api.config()]);
            setHealth(h);
            setConfig(c);
        } catch (e) {
            toast.error('Could not read system state', e.message);
        }
    }, [toast]);

    useEffect(() => { load(); }, [load]);

    const loadDoctor = useCallback(async () => {
        try {
            setDoctor(await api.doctor());
        } catch { /* nothing */ }
    }, []);

    useEffect(() => { loadDoctor(); }, [loadDoctor]);

    const runDiagnostics = async () => {
        setRunning(true);
        try {
            const result = await api.runDoctor();
            setDoctor(result);
            toast.success('Diagnostics started');
            // poll for completion
            const poll = setInterval(async () => {
                try {
                    const latest = await api.doctor();
                    setDoctor(latest);
                    if (latest.state !== 'running') {
                        clearInterval(poll);
                        setRunning(false);
                    }
                } catch {
                    clearInterval(poll);
                    setRunning(false);
                }
            }, 1000);
        } catch (e) {
            setRunning(false);
            toast.error('Diagnostics failed', e.message);
        }
    };

    const verdict = doctor?.verdict;
    const verdictInfo = verdict ? VERDICT[verdict.level] || VERDICT.warning : null;

    if (health === null || config === null) {
        return (
            <div className="grid gap-2.5 lg:grid-cols-2">
                <Skeleton className="h-64" />
                <Skeleton className="h-64" />
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
            {/* --- connection + status banner --- */}
            <Glass quiet className="flex flex-wrap items-center gap-3 rounded-b3 px-4 py-3">
                <Activity size={15} className="text-faint" />
                <div className="mr-auto">
                    <h1 className="font-display text-[13px] font-semibold text-text">System</h1>
                    <p className="text-[11px] text-faint">Health, configuration and diagnostics.</p>
                </div>
                <Badge color={connection === 'online' ? 'var(--flux-success)' : connection === 'connecting' ? 'var(--flux-think)' : 'var(--flux-err)'} dot>
                    {titleCase(connection)}
                </Badge>
                {status?.is_speaking && <Badge color="var(--flux-act)" dot>speaking</Badge>}
                {status?.is_sleeping && <Badge color="var(--flux-mute)" dot>asleep</Badge>}
            </Glass>

            {/* --- health checks --- */}
            <div className="grid gap-2.5 lg:grid-cols-3">
                <HealthCard
                    icon={Cpu}
                    label="LLM"
                    value={health.llm ? 'reachable' : 'unreachable'}
                    tone={health.llm ? 'var(--flux-success)' : 'var(--flux-err)'}
                    sub={health.llm_model}
                />
                <HealthCard
                    icon={Globe}
                    label="Web search"
                    value={health.search ? 'available' : 'unavailable'}
                    tone={health.search ? 'var(--flux-success)' : 'var(--flux-err)'}
                />
                <HealthCard
                    icon={HardDrive}
                    label="Memory"
                    value={health.memory ? 'ready' : 'offline'}
                    tone={health.memory ? 'var(--flux-success)' : 'var(--flux-err)'}
                    sub={health.memories_count ? `${compact(health.memories_count)} memories` : undefined}
                />
                <HealthCard
                    icon={Shield}
                    label="Cache"
                    value={health.cache || 'unknown'}
                    tone={health.cache === 'ready' ? 'var(--flux-success)' : 'var(--flux-think)'}
                />
                <HealthCard
                    icon={Network}
                    label="Network"
                    value={connection === 'online' ? 'connected' : 'offline'}
                    tone={connection === 'online' ? 'var(--flux-success)' : 'var(--flux-err)'}
                />
                <HealthCard
                    icon={Clock}
                    label="Uptime"
                    value={duration(status?.uptime)}
                    tone="var(--text)"
                />
            </div>

            {/* --- config overview --- */}
            <Glass quiet className="rounded-b3 p-4">
                <div className="mb-3 flex items-center gap-2.5">
                    <Info size={14} className="text-faint" />
                    <h2 className="font-display text-[13px] font-semibold text-text">Configuration</h2>
                    <span className="ml-auto text-[10px] font-mono text-faint">{Object.keys(config).length} keys</span>
                </div>
                <dl className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {Object.entries(config).slice(0, 12).map(([key, value]) => {
                        const display = typeof value === 'object' ? JSON.stringify(value) : String(value);
                        return (
                            <div key={key} className="rounded-b2 border border-line bg-fill px-3 py-2">
                                <dt className="font-mono text-[9px] uppercase tracking-wider text-faint">{titleCase(key)}</dt>
                                <dd className="mt-0.5 truncate font-mono text-[11px] text-dim" title={display}>
                                    {display || '—'}
                                </dd>
                            </div>
                        );
                    })}
                </dl>
            </Glass>

            {/* --- diagnostics --- */}
            <Glass quiet className="rounded-b3 p-4">
                <div className="mb-3 flex items-center gap-2.5">
                    <RefreshCw size={14} className={cn('text-faint', running && 'animate-spin')} />
                    <h2 className="font-display text-[13px] font-semibold text-text">Diagnostics</h2>
                    {verdictInfo && (
                        <Badge
                            color={verdictInfo.colour}
                            dot
                            style={{
                                borderColor: `color-mix(in srgb, ${verdictInfo.colour} 34%, transparent)`,
                                background: `color-mix(in srgb, ${verdictInfo.colour} 12%, transparent)`,
                            }}
                        >
                            {verdictInfo.label}
                        </Badge>
                    )}
                </div>

                {verdict && (
                    <div
                        className="mb-4 flex items-start gap-3 rounded-b2 border px-3.5 py-3"
                        style={{
                            borderColor: `color-mix(in srgb, ${verdictInfo.colour} 32%, transparent)`,
                            background: `color-mix(in srgb, ${verdictInfo.colour} 9%, transparent)`,
                        }}
                    >
                        <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full" style={{ background: `color-mix(in srgb, ${verdictInfo.colour} 18%, transparent)`, color: verdictInfo.colour }}>
                            <verdictInfo.icon size={12} strokeWidth={2.8} />
                        </span>
                        <div className="min-w-0">
                            <p className="text-[13px] font-semibold text-text">{verdict.headline}</p>
                            <p className="mt-0.5 text-[12px] leading-relaxed text-dim">{verdict.detail}</p>
                        </div>
                    </div>
                )}

                <Button variant={doctor?.findings?.length ? 'outline' : 'primary'} size="sm" onClick={runDiagnostics} loading={running}>
                    <RefreshCw size={13} /> {doctor?.findings?.length ? 'Run again' : 'Run diagnostics'}
                </Button>

                {doctor?.findings?.length > 0 && (
                    <ul className="mt-4 space-y-1">
                        {doctor.findings.map((finding) => {
                            const colour = finding.ok ? 'var(--flux-success)' : finding.blocking ? 'var(--flux-err)' : 'var(--flux-think)';
                            const Icon = finding.ok ? Check : finding.blocking ? AlertTriangle : AlertTriangle;
                            return (
                                <li key={finding.title} className="rounded-b2 px-1 py-1.5 transition-colors hover:bg-fill">
                                    <div className="flex items-start gap-2.5">
                                        <span className="mt-[2px] shrink-0" style={{ color: colour }}>
                                            <Icon size={13} strokeWidth={2.6} />
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-[12.5px] leading-snug">
                                                <span className="font-semibold text-text">{finding.title}</span>
                                                {finding.detail && <span className="ml-2 text-faint">{finding.detail}</span>}
                                            </p>
                                            {!finding.ok && finding.fix && (
                                                <pre className="mt-1.5 whitespace-pre-wrap rounded-b1 border border-line bg-fill px-2.5 py-2 font-mono text-[11px] leading-relaxed text-dim">
                                                    {finding.fix}
                                                </pre>
                                            )}
                                        </div>
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}

                {!doctor?.findings?.length && !running && (
                    <p className="mt-4 text-[12px] leading-relaxed text-faint">
                        Nothing has been checked yet. The run tests keys, the mind, memory, and the
                        dashboard — stopping at the first thing that would stop her.
                    </p>
                )}
            </Glass>
        </motion.div>
    );
}

function HealthCard({ icon: Icon, label, value, tone, sub }) {
    return (
        <Glass quiet className="flex items-center gap-3 rounded-b3 p-4">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-b2" style={{ background: `color-mix(in srgb, ${tone} 14%, transparent)`, color: tone }}>
                <Icon size={17} />
            </span>
            <div className="min-w-0 flex-1">
                <p className="font-mono text-[9px] uppercase tracking-wider text-faint">{label}</p>
                <p className="truncate font-display text-[13px] font-semibold text-text">{value}</p>
                {sub && <p className="truncate font-mono text-[10px] text-faint">{sub}</p>}
            </div>
        </Glass>
    );
}
