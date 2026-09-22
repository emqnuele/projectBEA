import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Boxes, Gamepad2, HeartHandshake, MessageCircle, Moon, Radio, Send, Settings2, Terminal, Users, Wifi, Zap } from 'lucide-react';
import { api } from '../api';
import { cn, fluxOf } from '../lib/cn';
import { clockTime, titleCase } from '../lib/format';
import { useStore } from '../store';
import { useToast } from '../state/ToastProvider';
import MinecraftConsole from '../components/console/MinecraftConsole';
import { Glass } from '../components/glass/Glass';
import { Button, Switch } from '../components/ui/controls';
import { Badge, Skeleton } from '../components/ui/feedback';

// catalogue groups abilities by their concern
const CATALOGUE = {
    monologue: { icon: Radio, title: 'Idle thoughts', group: 'Mind', blurb: 'She says something on her own when the room has gone quiet.' },
    memory: { icon: Users, title: 'Memory', group: 'Mind', blurb: 'Person cards, the diary and semantic recall.' },
    social_memory: { icon: HeartHandshake, title: 'Social memory', group: 'Mind', blurb: 'Who is who across platforms and how she feels about them.' },
    dream: { icon: Moon, title: 'Dreaming', group: 'Mind', blurb: 'While asleep she rereads the day and writes people down.' },
    minecraft: { icon: Gamepad2, title: 'Minecraft', group: 'World', blurb: 'A body on a vanilla server.' },
    twitch: { icon: MessageCircle, title: 'Twitch', group: 'Channels', blurb: 'Reads the stream chat and answers live.' },
    donations: { icon: Zap, title: 'Donations', group: 'Channels', blurb: 'Alerts reach her as perceptions.' },
    telegram: { icon: Send, title: 'Telegram', group: 'Channels', blurb: 'Private conversations that run beside everything else.' },
    discord: { icon: MessageCircle, title: 'Discord', group: 'Channels', blurb: 'Text channels and voice calls.' },
};

const GROUP_ORDER = ['Mind', 'World', 'Channels'];
const GROUP_ICONS = { Mind: Wifi, World: Gamepad2, Channels: Radio };

export default function SkillsPage() {
    const [skills, setSkills] = useState(null);
    const [config, setConfig] = useState(null);
    const [consoleOpen, setConsoleOpen] = useState(false);
    const [busy, setBusy] = useState(null);
    const refreshOverview = useStore((s) => s.refreshOverview);
    const { events } = useStore();
    const toast = useToast();

    const load = useCallback(async () => {
        try {
            const [runtime, settings] = await Promise.all([api.skills(), api.config()]);
            setSkills(runtime);
            setConfig(settings);
        } catch (e) {
            setSkills({});
            toast.error('Could not read her abilities', e.message);
        }
    }, [toast]);

    useEffect(() => {
        load();
        const timer = setInterval(() => api.skills().then(setSkills).catch(() => { }), 5000);
        return () => clearInterval(timer);
    }, [load]);

    const toggle = async (name, enable) => {
        setBusy(name);
        setSkills((prev) => ({ ...prev, [name]: { ...prev[name], enabled: enable } }));
        try {
            await api.toggleSkill(name, enable);
            toast.success(`${CATALOGUE[name]?.title || titleCase(name)} ${enable ? 'on' : 'off'}`);
            await refreshOverview();
        } catch (e) {
            setSkills((prev) => ({ ...prev, [name]: { ...prev[name], enabled: !enable } }));
            toast.error('That switch did not take', e.message);
        } finally {
            setBusy(null);
        }
    };

    const recent = useMemo(
        () => events.filter((e) => ['skill', 'error'].includes(e.category)).slice(0, 12),
        [events],
    );

    // --- group skills by category ---
    const grouped = useMemo(() => {
        if (!skills) return {};
        const groups = {};
        for (const [name, runtime] of Object.entries(skills)) {
            const group = CATALOGUE[name]?.group || 'Other';
            if (!groups[group]) groups[group] = [];
            groups[group].push({ name, runtime });
        }
        return groups;
    }, [skills]);

    if (skills === null) {
        return (
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-36" />)}
            </div>
        );
    }

    const totalEnabled = Object.values(skills).filter((s) => s.enabled).length;

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex h-full flex-col gap-2.5 overflow-y-auto pr-0.5"
        >
            {consoleOpen && (
                <MinecraftConsole
                    serverUrl={config?.skills?.minecraft?.server_url || 'ws://127.0.0.1:8080'}
                    onClose={() => setConsoleOpen(false)}
                />
            )}

            <Glass quiet className="flex flex-wrap items-center gap-3 rounded-b3 px-4 py-3">
                <Boxes size={15} className="text-faint" />
                <div className="mr-auto">
                    <h1 className="font-display text-[13px] font-semibold text-text">Abilities</h1>
                    <p className="text-[11px] text-faint">
                        A switch takes effect immediately. {totalEnabled} of {Object.keys(skills).length} enabled.
                    </p>
                </div>
            </Glass>

            {GROUP_ORDER.map((group) => {
                const items = grouped[group];
                if (!items) return null;
                const GroupIcon = GROUP_ICONS[group] || Boxes;
                return (
                    <div key={group}>
                        <div className="flex items-center gap-2 px-1 py-2">
                            <GroupIcon size={13} className="text-faint" />
                            <h2 className="font-mono text-[10px] uppercase tracking-widest text-faint">{group}</h2>
                            <div className="flex-1 border-t border-line" />
                        </div>
                        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                            {items.map(({ name, runtime }, index) => {
                                const meta = CATALOGUE[name] || { icon: Boxes, title: titleCase(name), blurb: '' };
                                const Icon = meta.icon;
                                return (
                                    <motion.div
                                        key={name}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: Math.min(index * 0.04, 0.32) }}
                                    >
                                        <Glass quiet className="flex h-full flex-col rounded-b3 p-4">
                                            <div className="flex items-start gap-3">
                                                <span
                                                    className="grid h-9 w-9 shrink-0 place-items-center rounded-b2"
                                                    style={{
                                                        background: runtime.active
                                                            ? 'color-mix(in srgb, var(--flux-act) 14%, transparent)'
                                                            : 'var(--fill-2)',
                                                        color: runtime.active ? 'var(--flux-act)' : 'var(--text-faint)',
                                                    }}
                                                >
                                                    <Icon size={17} />
                                                </span>
                                                <div className="min-w-0 flex-1">
                                                    <p className="truncate font-display text-sm font-semibold text-text">{meta.title}</p>
                                                    <p className="mt-0.5">
                                                        {runtime.active
                                                            ? <Badge color="var(--flux-act)" dot>running</Badge>
                                                            : runtime.enabled
                                                                ? <Badge dot>idle</Badge>
                                                                : <Badge color="var(--flux-mute)">off</Badge>}
                                                    </p>
                                                </div>
                                                <Switch
                                                    checked={runtime.enabled}
                                                    disabled={busy === name}
                                                    onChange={(value) => toggle(name, value)}
                                                    label={`Turn ${meta.title} ${runtime.enabled ? 'off' : 'on'}`}
                                                />
                                            </div>

                                            <p className="mt-3 text-[12px] leading-relaxed text-dim">{meta.blurb}</p>

                                            <div className="mt-auto flex items-center gap-2 pt-3.5">
                                                {name === 'minecraft' && (
                                                    <Button size="sm" variant="outline" onClick={() => setConsoleOpen(true)}>
                                                        <Terminal size={13} /> Console
                                                    </Button>
                                                )}
                                            </div>
                                        </Glass>
                                    </motion.div>
                                );
                            })}
                        </div>
                    </div>
                );
            })}

            {grouped.Other && grouped.Other.length > 0 && (
                <div>
                    <div className="flex items-center gap-2 px-1 py-2">
                        <Boxes size={13} className="text-faint" />
                        <h2 className="font-mono text-[10px] uppercase tracking-widest text-faint">Other</h2>
                        <div className="flex-1 border-t border-line" />
                    </div>
                    <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                        {grouped.Other.map(({ name, runtime }, index) => {
                            const meta = CATALOGUE[name] || { icon: Boxes, title: titleCase(name), blurb: '' };
                            const Icon = meta.icon;
                            return (
                                <motion.div
                                    key={name}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: Math.min(index * 0.04, 0.32) }}
                                >
                                    <Glass quiet className="flex h-full flex-col rounded-b3 p-4">
                                        <div className="flex items-start gap-3">
                                            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-b2" style={{ background: 'var(--fill-2)', color: 'var(--text-faint)' }}>
                                                <Icon size={17} />
                                            </span>
                                            <div className="min-w-0 flex-1">
                                                <p className="truncate font-display text-sm font-semibold text-text">{meta.title}</p>
                                                <p className="mt-0.5">
                                                    {runtime.active ? <Badge color="var(--flux-act)" dot>running</Badge>
                                                        : runtime.enabled ? <Badge dot>idle</Badge>
                                                        : <Badge color="var(--flux-mute)">off</Badge>}
                                                </p>
                                            </div>
                                            <Switch checked={runtime.enabled} disabled={busy === name} onChange={(v) => toggle(name, v)} label={`Toggle ${meta.title}`} />
                                        </div>
                                        {meta.blurb && <p className="mt-3 text-[12px] leading-relaxed text-dim">{meta.blurb}</p>}
                                    </Glass>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            )}

            <Glass quiet className="rounded-b3 p-4">
                <h2 className="mb-3 font-display text-[13px] font-semibold text-text">What they have been doing</h2>
                {recent.length === 0 ? (
                    <p className="py-6 text-center text-[12px] text-faint">No ability has done anything yet this run.</p>
                ) : (
                    <ul className="divide-y divide-[color:var(--line)]">
                        {recent.map((event) => {
                            const flux = fluxOf(event);
                            return (
                                <li key={event.id} className="flex items-start gap-3 py-2">
                                    <span className="tnum shrink-0 pt-px font-mono text-[10px] text-faint">{clockTime(event.timestamp)}</span>
                                    <span className="w-16 shrink-0 truncate font-mono text-[10px]" style={{ color: flux.color }}>{event.source}</span>
                                    <span className={cn('min-w-0 flex-1 break-words font-mono text-[11px]', event.category === 'error' ? 'text-[color:var(--flux-err)]' : 'text-dim')}>{event.message}</span>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Glass>
        </motion.div>
    );
}
