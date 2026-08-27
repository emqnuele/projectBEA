import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    ArrowUpRight, Blocks, Brain, Coins, Cpu, ListChecks, Radio, Sparkles, Square, Users,
    Volume2, WifiOff,
} from 'lucide-react';
import { api } from '../api';
import { cn, fluxOf } from '../lib/cn';
import { clockTime, compact, duration, relativeTime, titleCase } from '../lib/format';
import { useBrain } from '../state/BrainProvider';
import { useToast } from '../state/ToastProvider';
import { usePresence } from '../components/TopBar';
import { AttentionFlux } from '../components/AttentionFlux';
import { Glass } from '../components/glass/Glass';
import { Button } from '../components/ui/controls';
import { Badge, EmptyState, Skeleton } from '../components/ui/feedback';
import { AnimatedIcon, CountUp, ProgressRing } from '../components/motion/effects';

export default function HomePage() {
    const { overview, events, isSpeaking, isSleeping, status, connection, interrupt, toggleSleep, refreshOverview } = useBrain();
    const toast = useToast();
    const presence = usePresence();

    const lastSpoken = useMemo(() => events.find((e) => e.category === 'output'), [events]);
    const lastCost = useMemo(() => events.find((e) => e.source === 'cost'), [events]);
    const feed = useMemo(() => events.filter((e) => e.source !== 'attention').slice(0, 9), [events]);

    if (!overview) {
        // skeletons that pulse forever are a lie once we know the brain is gone
        return connection === 'offline'
            ? (
                <Glass quiet className="grid h-full place-items-center rounded-b3">
                    <EmptyState icon={WifiOff} title="Nothing to show — she is not running">
                        Start the engine with <code className="font-mono text-text">uv run bea --web</code> and
                        this fills itself in.
                        <span className="mt-5 block">
                            <Button variant="outline" size="sm" onClick={() => refreshOverview()}>Try again</Button>
                        </span>
                    </EmptyState>
                </Glass>
            )
            : <LoadingBento />;
    }

    const { plan, skills, memory, engine, session } = overview;
    const enabledSkills = skills.filter((s) => s.enabled);
    const progress = plan.total ? plan.closed / plan.total : 0;

    const guard = (action, failure) => async () => {
        try { await action(); } catch (e) { toast.error(failure, e.message); }
    };

    return (
        <div className="h-full overflow-y-auto pb-2 pr-0.5">
            <MeetHerBanner />
            <div className="grid auto-rows-min grid-cols-1 gap-2.5 md:grid-cols-6 xl:grid-cols-12">

                {/* --- the hero: is she alive, and what is she doing --- */}
                <Tile className="md:col-span-6 xl:col-span-5 xl:row-span-2">
                    <div className="flex h-full flex-col">
                        <div className="flex items-start gap-3">
                            <span
                                className="grid h-11 w-11 shrink-0 place-items-center rounded-b2"
                                style={{
                                    background: `color-mix(in srgb, ${presence.color} 16%, transparent)`,
                                    color: presence.color,
                                }}
                            >
                                <AnimatedIcon icon={presence.icon} state={presence.motion} size={19} />
                            </span>
                            <div className="min-w-0 flex-1">
                                <p className="font-mono text-[10px] uppercase tracking-widest text-faint">Right now</p>
                                <h2 className="font-display text-2xl font-bold leading-tight text-text">
                                    {presence.label}
                                </h2>
                            </div>
                            <Badge color={presence.color} dot>{isSleeping ? 'asleep' : 'awake'}</Badge>
                        </div>

                        <p className="mt-4 min-h-[3.2em] text-[13px] leading-relaxed text-dim">
                            {lastSpoken
                                ? <>“{lastSpoken.message}”</>
                                : 'She has not said anything yet in this run.'}
                        </p>
                        {lastSpoken && (
                            <p className="mt-1 font-mono text-[10px] text-faint">
                                said {relativeTime(lastSpoken.timestamp)}
                            </p>
                        )}

                        <div className="mt-auto grid grid-cols-3 gap-2 pt-5">
                            <MiniStat label="Awake for" value={duration(status?.uptime)} />
                            <MiniStat label="This chat" value={`${session.message_count} msgs`} />
                            <MiniStat label="Running" value={`${enabledSkills.length}/${skills.length}`} />
                        </div>

                        <div className="mt-3 flex flex-wrap gap-2">
                            {isSpeaking && (
                                <Button variant="vital" size="sm" onClick={guard(interrupt, 'Could not interrupt her')}>
                                    <Square size={11} className="fill-current" /> Stop her talking
                                </Button>
                            )}
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={guard(toggleSleep, isSleeping ? 'Could not wake her' : 'The dream pass failed')}
                            >
                                {isSleeping ? 'Wake her up' : 'Sleep and consolidate'}
                            </Button>
                            <Link
                                to="/dashboard/chat"
                                className="inline-flex h-8 items-center gap-1.5 rounded-b1 px-3 text-xs font-semibold text-dim transition-colors hover:bg-fill-2 hover:text-text"
                            >
                                Talk to her <ArrowUpRight size={13} />
                            </Link>
                        </div>
                    </div>
                </Tile>

                {/* --- the signature: what she chose to care about --- */}
                <Tile
                    className="md:col-span-6 xl:col-span-7"
                    title="Attention gate"
                    hint="Everything that reached her, and what she did with it"
                    to="/dashboard/activity"
                    icon={Brain}
                >
                    <AttentionFlux count={64} />
                </Tile>

                {/* --- today --- */}
                <Tile
                    className="md:col-span-3 xl:col-span-4"
                    title="Today"
                    hint="What she is working through"
                    to="/dashboard/plan"
                    icon={ListChecks}
                >
                    <div className="flex items-start gap-3.5">
                        <ProgressRing value={progress} size={46}>
                            <span className="tnum font-mono text-[10px] text-dim">
                                {Math.round(progress * 100)}%
                            </span>
                        </ProgressRing>
                        <div className="min-w-0 flex-1">
                            <p className={cn('text-[13px] font-medium leading-snug', plan.directive ? 'text-text' : 'text-faint')}>
                                {plan.directive || 'No orders for today. She will react, but she will not set out to do anything.'}
                            </p>
                            <p className="mt-1 font-mono text-[10px] text-faint">
                                {plan.closed} of {plan.total} closed
                            </p>
                        </div>
                    </div>

                    {plan.objectives.length > 0 && (
                        <ul className="mt-3.5 space-y-1.5 border-t border-line pt-3">
                            {plan.objectives.slice(0, 3).map((objective) => (
                                <li key={objective.id} className="flex items-center gap-2.5">
                                    <span
                                        className={cn('h-1.5 w-1.5 shrink-0 rounded-full', objective.status === 'doing' && 'animate-[bea-pulse_1.8s_ease-in-out_infinite]')}
                                        style={{ background: OBJECTIVE_COLOR[objective.status] }}
                                    />
                                    <span className={cn(
                                        'truncate text-xs',
                                        objective.status === 'done' || objective.status === 'dropped'
                                            ? 'text-faint line-through' : 'text-dim',
                                    )}>
                                        {objective.text}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    )}
                </Tile>

                {/* --- what the turns cost --- */}
                <Tile className="md:col-span-3 xl:col-span-3" title="Spend" icon={Coins}>
                    <p className="font-display text-3xl font-bold leading-none text-text">
                        <CountUp value={lastCost?.metadata?.session_tokens ?? 0} format={compact} />
                        <span className="ml-1.5 font-sans text-xs font-medium text-faint">tokens</span>
                    </p>
                    <p className="mt-2 text-[11px] leading-snug text-dim">
                        {lastCost
                            ? `Last turn took ${lastCost.metadata.steps} call(s) and ${lastCost.metadata.tokens} tokens.`
                            : 'No turn has been billed yet this run.'}
                    </p>
                </Tile>

                {/* --- the live feed --- */}
                <Tile
                    className="md:col-span-6 xl:col-span-8 xl:row-span-2"
                    title="Live"
                    hint="Perceptions, thoughts, actions"
                    to="/dashboard/activity"
                    icon={Radio}
                    bodyClassName="min-h-0"
                >
                    {feed.length === 0 ? (
                        <p className="py-8 text-center text-[13px] text-faint">Nothing has happened yet.</p>
                    ) : (
                        <ul className="divide-y divide-[color:var(--line)]">
                            {feed.map((event) => {
                                const flux = fluxOf(event);
                                return (
                                    <li key={event.id} className="flex items-start gap-3 py-2">
                                        <span className="tnum shrink-0 pt-px font-mono text-[10px] text-faint">
                                            {clockTime(event.timestamp)}
                                        </span>
                                        <span
                                            className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[9px] font-bold"
                                            style={{
                                                color: flux.color,
                                                background: `color-mix(in srgb, ${flux.color} 13%, transparent)`,
                                            }}
                                        >
                                            {flux.label}
                                        </span>
                                        <span className="min-w-0 flex-1 truncate text-xs text-dim">{event.message}</span>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </Tile>

                {/* --- memory --- */}
                <Tile
                    className="md:col-span-3 xl:col-span-4"
                    title="Memory"
                    hint="Who she knows"
                    to="/dashboard/memory"
                    icon={Users}
                >
                    <div className="grid grid-cols-3 gap-2">
                        <MiniStat label="People" value={<CountUp value={memory.people} />} />
                        <MiniStat label="Seen" value={<CountUp value={memory.roster} />} />
                        <MiniStat label="Memories" value={<CountUp value={memory.memories} format={compact} />} />
                    </div>
                    <p className="mt-3 text-[11px] leading-snug text-dim">
                        {memory.rag_ready
                            ? `${memory.self_facts} things she has worked out about herself, ${memory.hot_facts} live right now.`
                            : 'Recall is off — enable the memory ability to let her search what she remembers.'}
                    </p>
                </Tile>

                {/* --- engine --- */}
                <Tile className="md:col-span-3 xl:col-span-4" title="Engine" to="/dashboard/settings/engine" icon={Cpu}>
                    <dl className="space-y-2">
                        <EngineRow label="Thinks with" value={engine.model || '—'} sub={engine.llm_provider} />
                        <EngineRow label="Speaks with" value={engine.tts_provider} icon={Volume2} />
                        <EngineRow label="Hears with" value={engine.stt_provider} />
                        <EngineRow
                            label="OBS"
                            value={engine.obs_connected ? 'connected' : 'not connected'}
                            tone={engine.obs_connected ? 'var(--flux-act)' : 'var(--flux-mute)'}
                        />
                    </dl>
                </Tile>

                {/* --- abilities --- */}
                <Tile
                    className="md:col-span-6 xl:col-span-12"
                    title="Abilities"
                    hint={`${enabledSkills.length} of ${skills.length} on`}
                    to="/dashboard/skills"
                    icon={Blocks}
                >
                    <div className="flex flex-wrap gap-1.5">
                        {skills.map((skill) => (
                            <span
                                key={skill.name}
                                className={cn(
                                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium',
                                    skill.enabled ? 'text-text' : 'text-faint',
                                )}
                                style={{
                                    borderColor: skill.active
                                        ? 'color-mix(in srgb, var(--flux-act) 40%, transparent)'
                                        : 'var(--line)',
                                    background: skill.active
                                        ? 'color-mix(in srgb, var(--flux-act) 10%, transparent)'
                                        : 'transparent',
                                }}
                            >
                                <span
                                    className={cn('h-1.5 w-1.5 rounded-full', skill.active && 'animate-[bea-pulse_2s_ease-in-out_infinite]')}
                                    style={{ background: skill.active ? 'var(--flux-act)' : skill.enabled ? 'var(--text-dim)' : 'var(--flux-mute)' }}
                                />
                                {titleCase(skill.name)}
                            </span>
                        ))}
                    </div>
                </Tile>
            </div>
        </div>
    );
}

const OBJECTIVE_COLOR = {
    todo: 'var(--text-faint)',
    doing: 'var(--vital)',
    done: 'var(--flux-act)',
    dropped: 'var(--flux-mute)',
};

function Tile({ title, hint, to, icon: Icon, children, className, bodyClassName }) {
    const head = (title || Icon) && (
        <div className="mb-3.5 flex items-center gap-2.5">
            {Icon && <Icon size={14} className="shrink-0 text-faint" />}
            <div className="min-w-0 flex-1">
                <h3 className="truncate font-display text-[13px] font-semibold text-text">{title}</h3>
                {hint && <p className="truncate text-[11px] text-faint">{hint}</p>}
            </div>
            {to && <ArrowUpRight size={14} className="shrink-0 text-faint transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />}
        </div>
    );

    const body = (
        <>
            {head}
            <div className={cn('flex-1', bodyClassName)}>{children}</div>
        </>
    );

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            className={className}
        >
            <Glass
                quiet
                className={cn(
                    'group flex h-full flex-col transition-colors duration-200',
                    to && 'hover:border-line-strong hover:bg-fill-2',
                )}
            >
                {to
                    ? <Link to={to} className="flex h-full flex-col rounded-[inherit] p-4">{body}</Link>
                    : <div className="flex h-full flex-col p-4">{body}</div>}
            </Glass>
        </motion.div>
    );
}

function MiniStat({ label, value }) {
    return (
        <div className="rounded-b2 border border-line bg-fill px-2.5 py-2">
            <p className="truncate font-mono text-[9px] uppercase tracking-wider text-faint">{label}</p>
            <p className="tnum mt-0.5 truncate font-display text-sm font-semibold text-text">{value}</p>
        </div>
    );
}

function EngineRow({ label, value, sub, tone }) {
    return (
        <div className="flex items-baseline gap-3">
            <dt className="shrink-0 text-[11px] text-faint">{label}</dt>
            <dd className="ml-auto min-w-0 truncate text-right">
                <span className="block truncate font-mono text-[11px]" style={{ color: tone || 'var(--text)' }}>
                    {value}
                </span>
                {sub && <span className="block truncate text-[10px] text-faint">{sub}</span>}
            </dd>
        </div>
    );
}

function LoadingBento() {
    return (
        <div className="grid auto-rows-min grid-cols-1 gap-2.5 md:grid-cols-6 xl:grid-cols-12">
            <Skeleton className="h-64 md:col-span-6 xl:col-span-5 xl:row-span-2" />
            <Skeleton className="h-40 md:col-span-6 xl:col-span-7" />
            <Skeleton className="h-40 md:col-span-3 xl:col-span-4" />
            <Skeleton className="h-40 md:col-span-3 xl:col-span-3" />
            <Skeleton className="h-56 md:col-span-6 xl:col-span-8" />
            <Skeleton className="h-40 md:col-span-3 xl:col-span-4" />
        </div>
    );
}


/**
 * The one thing a fresh install is missing.
 *
 * The setup script arms the plumbing and never asks who she is, so without
 * this almost everyone runs the shipped character forever. It shows once,
 * closes for good, and never blocks the dashboard behind it.
 */
function MeetHerBanner() {
    const [needed, setNeeded] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        let alive = true;
        api.onboarding()
            .then((data) => { if (alive) setNeeded(Boolean(data.needed)); })
            .catch(() => { /* a missing banner is not worth an error */ });
        return () => { alive = false; };
    }, []);

    const dismiss = async () => {
        setNeeded(false);
        try { await api.skipOnboarding(); } catch { /* nothing to recover */ }
    };

    if (!needed) return null;

    return (
        <Glass quiet className="mb-2.5 flex flex-wrap items-center justify-between gap-3 rounded-b3 p-4">
            <div className="min-w-0">
                <h2 className="font-display text-[13px] font-semibold text-text">
                    She does not have a character yet
                </h2>
                <p className="mt-1 text-[11px] leading-snug text-faint">
                    She is running the one we ship. Six questions and she is someone of yours.
                </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
                <Button variant="ghost" size="sm" onClick={dismiss}>Not now</Button>
                <Button variant="primary" size="sm" onClick={() => navigate('/dashboard/onboarding')}>
                    <Sparkles size={13} /> Set her up
                </Button>
            </div>
        </Glass>
    );
}
