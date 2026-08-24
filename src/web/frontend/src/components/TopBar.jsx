import React, { useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Menu, Moon, Radio, Search, Square, Sun, SunMoon, Zap } from 'lucide-react';
import { cn } from '../lib/cn';
import { compact } from '../lib/format';
import { useBrain } from '../state/BrainProvider';
import { useAppearance } from '../state/AppearanceProvider';
import { useToast } from '../state/ToastProvider';
import { Glass } from './glass/Glass';
import { Button, IconButton } from './ui/controls';
import { AnimatedIcon, CountUp } from './motion/effects';

/** Sleeping · Speaking · Thinking · Listening — derived once, shown everywhere. */
export function usePresence() {
    const { events, isSpeaking, isSleeping, now } = useBrain();

    return useMemo(() => {
        if (isSleeping) return { key: 'sleeping', label: 'Sleeping', detail: 'Consolidating memory', color: 'var(--flux-think)', icon: Moon, motion: 'breathe' };
        if (isSpeaking) return { key: 'speaking', label: 'Speaking', detail: 'Audio is going out', color: 'var(--vital)', icon: Radio, motion: 'pulse' };

        const latest = events.find((e) => e.source !== 'attention');
        const fresh = latest && now - latest.timestamp < 6;
        if (fresh && (latest.category === 'thought' || latest.category === 'input')) {
            return { key: 'thinking', label: 'Thinking', detail: latest.message?.slice(0, 60) || '', color: 'var(--flux-think)', icon: Zap, motion: 'pulse' };
        }
        return { key: 'listening', label: 'Listening', detail: 'Waiting for something worth a thought', color: 'var(--flux-in)', icon: Radio, motion: 'breathe' };
    }, [events, isSpeaking, isSleeping, now]);
}

export function TopBar({ onOpenMenu, onOpenPalette }) {
    const { events, isSpeaking, isSleeping, activeSkills, interrupt, toggleSleep, connection, streaming } = useBrain();
    const { settings, toggleTheme } = useAppearance();
    const toast = useToast();
    const presence = usePresence();

    const sessionTokens = useMemo(() => {
        const cost = events.find((e) => e.source === 'cost');
        return cost?.metadata?.session_tokens ?? null;
    }, [events]);

    const run = (action, failure) => async () => {
        try {
            await action();
        } catch (e) {
            toast.error(failure, e.message);
        }
    };

    return (
        <Glass
            as="header"
            className="flex h-14 shrink-0 items-center gap-2 rounded-b3 px-2.5 sm:gap-3 sm:px-3.5"
        >
            <IconButton label="Open menu" onClick={onOpenMenu} className="lg:hidden">
                <Menu size={17} />
            </IconButton>

            <div className="flex min-w-0 items-center gap-2.5">
                <span
                    className="relative grid h-8 w-8 shrink-0 place-items-center rounded-full"
                    style={{ background: `color-mix(in srgb, ${presence.color} 16%, transparent)`, color: presence.color }}
                >
                    <AnimatedIcon icon={presence.icon} state={presence.motion} size={15} />
                </span>
                <span className="min-w-0">
                    <span className="flex items-baseline gap-2">
                        <span className="font-display text-[13px] font-semibold leading-none text-text">
                            {presence.label}
                        </span>
                        {activeSkills.length > 0 && (
                            <span className="hidden font-mono text-[10px] uppercase tracking-wider text-faint sm:inline">
                                {activeSkills.length} running
                            </span>
                        )}
                    </span>
                    <span className="mt-1 hidden truncate text-[11px] leading-none text-faint sm:block">
                        {presence.detail}
                    </span>
                </span>
            </div>

            <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
                {sessionTokens !== null && (
                    <span className="hidden items-center gap-1.5 rounded-full border border-line px-2.5 py-1 font-mono text-[10px] text-dim md:inline-flex">
                        <CountUp value={sessionTokens} format={compact} />
                        <span className="text-faint">tokens</span>
                    </span>
                )}

                <span
                    className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider sm:inline-flex"
                    style={connection === 'online'
                        ? { color: 'var(--flux-act)', borderColor: 'color-mix(in srgb, var(--flux-act) 30%, transparent)' }
                        : { color: 'var(--flux-err)', borderColor: 'color-mix(in srgb, var(--flux-err) 34%, transparent)' }}
                >
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                    {connection === 'online' ? (streaming ? 'live' : 'polling') : 'offline'}
                </span>

                <AnimatePresence>
                    {isSpeaking && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9, width: 0 }}
                            animate={{ opacity: 1, scale: 1, width: 'auto' }}
                            exit={{ opacity: 0, scale: 0.9, width: 0 }}
                        >
                            <Button variant="vital" size="sm" onClick={run(interrupt, 'Could not interrupt her')}>
                                <Square size={11} className="fill-current" />
                                Stop
                            </Button>
                        </motion.div>
                    )}
                </AnimatePresence>

                <IconButton
                    label={isSleeping ? 'Wake her up' : 'Put her to sleep and consolidate memory'}
                    onClick={run(toggleSleep, isSleeping ? 'Could not wake her' : 'The dream pass failed')}
                    className={cn(isSleeping && 'text-[color:var(--flux-think)]')}
                >
                    {isSleeping ? <Sun size={16} /> : <Moon size={16} />}
                </IconButton>

                <IconButton label="Search and commands" onClick={onOpenPalette}>
                    <Search size={16} />
                </IconButton>

                <IconButton
                    label={settings.theme === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'}
                    onClick={toggleTheme}
                >
                    <SunMoon size={16} />
                </IconButton>
            </div>
        </Glass>
    );
}
