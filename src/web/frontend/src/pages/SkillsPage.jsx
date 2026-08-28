import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Boxes, Coins, Gamepad2, HeartHandshake, MessageCircle, Moon, Radio, Send, Settings2, Terminal, Users,
} from 'lucide-react';
import { api } from '../api';
import { cn, fluxOf } from '../lib/cn';
import { clockTime, titleCase } from '../lib/format';
import { useBrain } from '../state/BrainProvider';
import { useToast } from '../state/ToastProvider';
import MinecraftConsole from '../components/console/MinecraftConsole';
import { Glass } from '../components/glass/Glass';
import { Button, Switch } from '../components/ui/controls';
import { Badge, Skeleton } from '../components/ui/feedback';

// what each ability actually does, in the operator's words
const CATALOGUE = {
    monologue: {
        icon: Radio, title: 'Idle thoughts',
        blurb: 'She says something on her own when the room has gone quiet for a while.',
        settings: null,
    },
    memory: {
        icon: Users, title: 'Memory',
        blurb: 'Person cards, the diary and semantic recall. Without this she forgets everyone between sessions.',
        settings: 'mind',
    },
    social_memory: {
        icon: HeartHandshake, title: 'Social memory',
        blurb: 'Keeps track of who is who across platforms and how she feels about them.',
        settings: 'mind',
    },
    dream: {
        icon: Moon, title: 'Dreaming',
        blurb: 'While asleep she rereads the day, writes people down and works out things about herself.',
        settings: 'mind',
    },
    minecraft: {
        icon: Gamepad2, title: 'Minecraft',
        blurb: 'A body on a vanilla server. She plays toward the objectives you set and reads game chat.',
        settings: 'world',
    },
    twitch: {
        icon: MessageCircle, title: 'Twitch',
        blurb: 'Reads the stream chat and answers the parts that concern her.',
        settings: 'channels',
    },
    donations: {
        icon: Coins, title: 'Donations',
        blurb: 'Alerts reach her as perceptions, so she can react to them live.',
        settings: 'channels',
    },
    telegram: {
        icon: Send, title: 'Telegram',
        blurb: 'Private conversations that run beside everything else.',
        settings: 'channels',
    },
    discord: {
        icon: MessageCircle, title: 'Discord',
        blurb: 'Text channels and voice calls, each one its own conversation.',
        settings: 'channels',
    },
};

export default function SkillsPage() {
    const [skills, setSkills] = useState(null);
    const [config, setConfig] = useState(null);
    const [consoleOpen, setConsoleOpen] = useState(false);
    const [busy, setBusy] = useState(null);

    const { events, refreshOverview } = useBrain();
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
        // optimistic: the switch must answer the finger, not the round trip
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

    if (skills === null) {
        return (
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-36" />)}
            </div>
        );
    }

    const entries = Object.entries(skills);

    return (
        <div className="flex h-full flex-col gap-2.5 overflow-y-auto pr-0.5">
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
                        A switch takes effect immediately. Everything each one needs to be configured lives in Settings.
                    </p>
                </div>
            </Glass>

            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                {entries.map(([name, runtime], index) => {
                    const meta = CATALOGUE[name] || { icon: Boxes, title: titleCase(name), blurb: '', settings: null };
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
                                    {meta.settings && (
                                        <Link
                                            to={`/dashboard/settings/${meta.settings}`}
                                            className="inline-flex h-8 items-center gap-1.5 rounded-b1 px-2.5 text-xs
                                                       font-semibold text-dim transition-colors hover:bg-fill-2 hover:text-text"
                                        >
                                            <Settings2 size={13} /> Configure
                                        </Link>
                                    )}
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

            <Glass quiet className="rounded-b3 p-4">
                <h2 className="mb-3 font-display text-[13px] font-semibold text-text">What they have been doing</h2>
                {recent.length === 0 ? (
                    <p className="py-6 text-center text-[12px] text-faint">
                        No ability has done anything yet this run.
                    </p>
                ) : (
                    <ul className="divide-y divide-[color:var(--line)]">
                        {recent.map((event) => {
                            const flux = fluxOf(event);
                            return (
                                <li key={event.id} className="flex items-start gap-3 py-2">
                                    <span className="tnum shrink-0 pt-px font-mono text-[10px] text-faint">
                                        {clockTime(event.timestamp)}
                                    </span>
                                    <span
                                        className="w-16 shrink-0 truncate font-mono text-[10px]"
                                        style={{ color: flux.color }}
                                    >
                                        {event.source}
                                    </span>
                                    <span className={cn(
                                        'min-w-0 flex-1 break-words font-mono text-[11px]',
                                        event.category === 'error' ? 'text-[color:var(--flux-err)]' : 'text-dim',
                                    )}>
                                        {event.message}
                                    </span>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Glass>
        </div>
    );
}
