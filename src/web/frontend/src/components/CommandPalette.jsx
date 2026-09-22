import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CornerDownLeft, Moon, Search, Square, Sun } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { SURFACES } from '../lib/nav';
import { useStore } from '../store';
import { Modal } from './ui/Modal';

export function CommandPalette({ open, onClose }) {
    const [query, setQuery] = useState('');
    const [cursor, setCursor] = useState(0);
    const listRef = useRef(null);

    const navigate = useNavigate();
    const { status, theme, toggleTheme } = useStore();

    const commands = useMemo(() => {
        const go = (to) => () => navigate(to);
        const items = SURFACES.map((item) => ({
            id: item.to,
            label: item.label,
            hint: item.hint,
            group: 'Go to',
            icon: item.icon,
            run: go(item.to),
        }));

        items.push(
            {
                id: 'sleep',
                label: 'Run a dream pass',
                hint: 'Consolidates memory overnight',
                group: 'Do',
                icon: Moon,
                run: async () => { await api.dreamRun(); },
            },
            {
                id: 'theme',
                label: theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
                group: 'Do',
                icon: theme === 'dark' ? Sun : Moon,
                run: toggleTheme,
            },
        );

        return items;
    }, [navigate, toggleTheme, theme]);

    const results = useMemo(() => {
        const needle = query.trim().toLowerCase();
        const matched = needle
            ? commands.filter((c) => c.label.toLowerCase().includes(needle) || c.hint?.toLowerCase().includes(needle))
            : commands;
        return matched.map((command, index, all) => ({
            ...command,
            startsGroup: index === 0 || all[index - 1].group !== command.group,
        }));
    }, [commands, query]);

    useEffect(() => { setCursor(0); }, [query, open]);
    useEffect(() => { if (open) setQuery(''); }, [open]);

    const runAt = async (index) => {
        const command = results[index];
        if (!command) return;
        onClose();
        try {
            await command.run();
        } catch (e) {}
    };

    const onKeyDown = (event) => {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            setCursor((c) => Math.min(c + 1, results.length - 1));
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
        } else if (event.key === 'Enter') {
            event.preventDefault();
            runAt(cursor);
        }
    };

    useEffect(() => {
        listRef.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' });
    }, [cursor]);

    return (
        <Modal open={open} onClose={onClose} size="md">
            <div className="-mx-5 -my-4">
                <div className="flex items-center gap-3 border-b border-line px-4 py-3">
                    <Search size={16} className="shrink-0 text-faint" />
                    <input
                        autoFocus
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={onKeyDown}
                        placeholder="Where to, or what should she do?"
                        aria-label="Search commands"
                        className="bare w-full bg-transparent text-sm text-text outline-none placeholder:text-faint"
                    />
                    <kbd className="hidden shrink-0 rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-faint sm:block">
                        esc
                    </kbd>
                </div>

                <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-2">
                    {results.length === 0 && (
                        <p className="px-3 py-6 text-center text-[13px] text-faint">
                            Nothing matches "{query}".
                        </p>
                    )}
                    {results.map((command, index) => {
                        const active = index === cursor;
                        const Icon = command.icon;
                        return (
                            <React.Fragment key={command.id}>
                                {command.startsGroup && (
                                    <p className="px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-widest text-faint">
                                        {command.group}
                                    </p>
                                )}
                                <button
                                    data-active={active}
                                    onMouseEnter={() => setCursor(index)}
                                    onClick={() => runAt(index)}
                                    className={cn(
                                        'flex w-full items-center gap-3 rounded-b2 px-3 py-2 text-left transition-colors',
                                        active ? 'bg-fill-3 text-text' : 'text-dim hover:text-text',
                                    )}
                                >
                                    {Icon ? <Icon size={15} className="shrink-0 text-faint" /> : <span className="w-[15px]" />}
                                    <span className="min-w-0 flex-1">
                                        <span className="block truncate text-[13px] font-medium">{command.label}</span>
                                        {command.hint && (
                                            <span className="block truncate text-[11px] text-faint">{command.hint}</span>
                                        )}
                                    </span>
                                    {active && <CornerDownLeft size={13} className="shrink-0 text-faint" />}
                                </button>
                            </React.Fragment>
                        );
                    })}
                </div>
            </div>
        </Modal>
    );
}
