import React, { useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Menu, Moon, Radio, Search, Square, Sun, WifiOff, Zap } from 'lucide-react';
import { cn } from '../lib/cn';
import { useStore } from '../store';
import { api } from '../api';
import { Glass } from './glass/Glass';
import { Button, IconButton } from './ui/controls';
import { AnimatedIcon } from './motion/effects';

export function TopBar({ onOpenMenu, onOpenPalette }) {
    const { connection, streaming, status, toggleTheme, theme } = useStore();
    const isSpeaking = Boolean(status?.is_speaking);
    const isSleeping = Boolean(status?.is_sleeping);

    const presence = useMemo(() => {
        if (isSleeping) return { key: 'sleeping', label: 'Dreaming', detail: 'Consolidating memory', color: 'var(--dream)', icon: Moon, motion: 'breathe' };
        if (isSpeaking) return { key: 'speaking', label: 'Speaking', detail: 'Audio is going out', color: 'var(--vital)', icon: Radio, motion: 'pulse' };
        return { key: 'idle', label: 'Active', detail: 'Waiting for input', color: 'var(--flux-in)', icon: Zap, motion: 'breathe' };
    }, [isSpeaking, isSleeping]);

    const run = (action, failure) => async () => {
        try { await action(); } catch {}
    };

    return (
        <Glass as="header" className="flex h-14 shrink-0 items-center gap-2.5 rounded-b3 px-2.5 sm:gap-3 sm:px-3.5">
            <IconButton label="Open menu" onClick={onOpenMenu} className="lg:hidden">
                <Menu size={17} />
            </IconButton>

            <div className="flex min-w-0 items-center gap-2.5">
                <span className="relative grid h-8 w-8 shrink-0 place-items-center rounded-full" style={{ background: `color-mix(in srgb, ${presence.color} 16%, transparent)`, color: presence.color }}>
                    <AnimatedIcon icon={presence.icon} state={presence.motion} size={15} />
                </span>
                <span className="min-w-0">
                    <span className="flex items-baseline gap-2">
                        <span className="font-display text-[13px] font-semibold leading-none text-text">{presence.label}</span>
                        <span className="hidden font-mono text-[10px] uppercase tracking-wider text-faint sm:inline">SHURA</span>
                    </span>
                    <span className="mt-1 hidden truncate text-[11px] leading-none text-faint sm:block">{presence.detail}</span>
                </span>
            </div>

            <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
                {/* connection badge */}
                <span className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider sm:inline-flex" style={connection === 'online' ? { color: 'var(--flux-success)', borderColor: 'color-mix(in srgb, var(--flux-success) 30%, transparent)' } : { color: 'var(--flux-err)', borderColor: 'color-mix(in srgb, var(--flux-err) 34%, transparent)' }}>
                    <span className="h-1.5 w-1.5 rounded-full bg-current" />
                    {connection === 'online' ? (streaming ? 'live' : 'connected') : 'offline'}
                </span>

                <AnimatePresence>
                    {isSpeaking && (
                        <motion.div initial={{ opacity: 0, scale: 0.9, width: 0 }} animate={{ opacity: 1, scale: 1, width: 'auto' }} exit={{ opacity: 0, scale: 0.9, width: 0 }}>
                            <Button variant="vital" size="sm" onClick={run(() => api.interrupt(), 'Could not interrupt')}>
                                <Square size={11} className="fill-current" />
                                Stop
                            </Button>
                        </motion.div>
                    )}
                </AnimatePresence>

                <IconButton label="Search and commands" onClick={onOpenPalette}>
                    <Search size={16} />
                </IconButton>

                <IconButton label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggleTheme}>
                    {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                </IconButton>
            </div>
        </Glass>
    );
}
