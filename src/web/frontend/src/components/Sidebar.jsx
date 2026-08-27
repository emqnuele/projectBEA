import React, { useCallback, useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
    Check, ChevronLeft, MessageSquarePlus, PanelLeft, Pencil, Settings, Trash2, X,
} from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { NAV, VERSION } from '../lib/nav';
import { relativeTime } from '../lib/format';
import { DESKTOP, useMediaQuery } from '../hooks/useMediaQuery';
import { useToast } from '../state/ToastProvider';
import { useDialog } from '../state/DialogProvider';
import { useBrain } from '../state/BrainProvider';
import { Glass } from './glass/Glass';
import { IconButton } from './ui/controls';
import { Spinner } from './ui/feedback';

const COLLAPSE_KEY = 'bea.sidebar.collapsed';

export function Sidebar({ mobileOpen, onCloseMobile }) {
    const [collapsedPreference, setCollapsedPreference] = useState(
        () => localStorage.getItem(COLLAPSE_KEY) === '1',
    );
    const [sessions, setSessions] = useState(null);
    const [renaming, setRenaming] = useState(null);
    const [draftTitle, setDraftTitle] = useState('');

    const navigate = useNavigate();
    const toast = useToast();
    const dialog = useDialog();
    const isDesktop = useMediaQuery(DESKTOP);
    const { status, refreshOverview, name } = useBrain();
    const activeSession = status?.session_id;

    // the rail only narrows on desktop: on a phone this is a drawer that slides
    // over the page, and a 74px drawer would be a worse version of the menu
    const rail = collapsedPreference && isDesktop;

    useEffect(() => {
        localStorage.setItem(COLLAPSE_KEY, collapsedPreference ? '1' : '0');
    }, [collapsedPreference]);

    const loadSessions = useCallback(async () => {
        try {
            setSessions(await api.sessions());
        } catch {
            setSessions([]);
        }
    }, []);

    useEffect(() => { loadSessions(); }, [loadSessions, activeSession]);

    const startNewChat = async () => {
        const ok = await dialog.confirm({
            title: 'Start a new conversation?',
            message: 'The current one is saved and closed. She keeps what she learned from it.',
            confirmLabel: 'Start new',
        });
        if (!ok) return;
        try {
            await api.createSession();
            await loadSessions();
            await refreshOverview();
            navigate('/dashboard/chat');
            toast.success('New conversation started');
        } catch (e) {
            toast.error('Could not start a conversation', e.message);
        }
    };

    const openSession = async (id) => {
        try {
            await api.activateSession(id);
            await loadSessions();
            navigate('/dashboard/chat');
        } catch (e) {
            toast.error('Could not open that conversation', e.message);
        }
    };

    const saveTitle = async (id) => {
        const title = draftTitle.trim();
        setRenaming(null);
        if (!title) return;
        try {
            await api.renameSession(id, title);
            await loadSessions();
        } catch (e) {
            toast.error('Could not rename it', e.message);
        }
    };

    const removeSession = async (session) => {
        const ok = await dialog.confirm({
            title: `Delete "${sessionLabel(session)}"?`,
            message: 'The transcript is removed from disk. What she already remembers from it stays.',
            confirmLabel: 'Delete',
            danger: true,
        });
        if (!ok) return;
        try {
            await api.deleteSession(session.id);
            await loadSessions();
            toast.success('Conversation deleted');
        } catch (e) {
            toast.error('Could not delete it', e.message);
        }
    };

    return (
        <>
            <AnimatePresence>
                {mobileOpen && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        onClick={onCloseMobile}
                        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] lg:hidden"
                    />
                )}
            </AnimatePresence>

            <Glass
                as="nav"
                aria-label="Sections"
                className={cn(
                    'fixed inset-y-0 left-0 z-50 flex w-[264px] flex-col overflow-hidden rounded-none border-y-0 border-l-0 p-3',
                    'transition-transform duration-300 lg:static lg:z-auto lg:h-full lg:rounded-b4 lg:border',
                    'lg:translate-x-0 lg:transition-[width] lg:duration-300',
                    rail ? 'lg:w-[76px]' : 'lg:w-[248px]',
                    mobileOpen ? 'translate-x-0' : '-translate-x-full',
                )}
            >
                <header
                    className={cn(
                        'mb-3 flex shrink-0 items-center pt-0.5',
                        rail ? 'justify-center' : 'gap-2 px-1',
                    )}
                >
                    <BrandMark rail={rail} />
                    {!rail && (
                        <IconButton
                            label="Collapse the sidebar"
                            size="sm"
                            onClick={() => setCollapsedPreference(true)}
                            className="ml-auto max-lg:hidden"
                        >
                            <ChevronLeft size={14} />
                        </IconButton>
                    )}
                    <IconButton label="Close the menu" size="sm" onClick={onCloseMobile} className="ml-auto lg:hidden">
                        <X size={15} />
                    </IconButton>
                </header>

                <ul className="shrink-0 space-y-0.5">
                    {NAV.map((item) => (
                        <li key={item.to}>
                            <NavLink
                                to={item.to}
                                end={item.end}
                                onClick={onCloseMobile}
                                title={rail ? item.label : undefined}
                                className={({ isActive }) => cn(
                                    'group relative flex items-center rounded-b2 py-2 text-[13px] font-medium transition-colors',
                                    rail ? 'justify-center px-0' : 'gap-3 px-2.5',
                                    isActive ? 'text-text' : 'text-dim hover:bg-fill-2 hover:text-text',
                                )}
                            >
                                {({ isActive }) => (
                                    <>
                                        {isActive && (
                                            <motion.span
                                                layoutId="nav-active"
                                                transition={{ type: 'spring', stiffness: 520, damping: 40 }}
                                                className="absolute inset-0 rounded-b2 border border-line bg-fill-3"
                                            />
                                        )}
                                        <span className="relative shrink-0"><item.icon size={17} /></span>
                                        {!rail && <span className="relative truncate">{item.label}</span>}
                                        {isActive && !rail && (
                                            <span
                                                className="relative ml-auto h-1.5 w-1.5 rounded-full"
                                                style={{ background: 'var(--vital)' }}
                                            />
                                        )}
                                    </>
                                )}
                            </NavLink>
                        </li>
                    ))}
                </ul>

                <div className="mt-4 flex min-h-0 flex-1 flex-col">
                    <div className={cn('mb-2 flex shrink-0 items-center', rail ? 'justify-center' : 'gap-2 px-2.5')}>
                        {!rail && (
                            <span className="text-[10px] font-semibold uppercase tracking-widest text-faint">
                                Conversations
                            </span>
                        )}
                        <IconButton
                            label="New conversation"
                            size="sm"
                            onClick={startNewChat}
                            className={cn(!rail && 'ml-auto')}
                        >
                            <MessageSquarePlus size={15} />
                        </IconButton>
                    </div>

                    {!rail && (
                        <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto pb-2 pr-0.5">
                            {sessions === null && (
                                <div className="flex justify-center py-4"><Spinner /></div>
                            )}
                            {sessions?.length === 0 && (
                                <p className="px-2.5 py-2 text-[11px] leading-snug text-faint">
                                    Nothing yet. Say something to her and it lands here.
                                </p>
                            )}
                            {sessions?.map((session) => {
                                const isActive = session.id === activeSession;
                                if (renaming === session.id) {
                                    return (
                                        <div key={session.id} className="flex items-center gap-1 px-1 py-1">
                                            <input
                                                autoFocus
                                                value={draftTitle}
                                                onChange={(e) => setDraftTitle(e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') saveTitle(session.id);
                                                    if (e.key === 'Escape') setRenaming(null);
                                                }}
                                                aria-label="Conversation name"
                                                className="min-w-0 flex-1 rounded-b1 border border-line-strong bg-fill-2 px-2 py-1 text-xs text-text outline-none"
                                            />
                                            <IconButton label="Save the name" size="sm" onClick={() => saveTitle(session.id)}>
                                                <Check size={13} />
                                            </IconButton>
                                        </div>
                                    );
                                }
                                return (
                                    <div
                                        key={session.id}
                                        className={cn(
                                            'group flex items-center gap-1 rounded-b2 px-1 transition-colors',
                                            isActive
                                                ? 'border border-line bg-fill-3'
                                                : 'border border-transparent hover:bg-fill',
                                        )}
                                    >
                                        <button
                                            onClick={() => openSession(session.id)}
                                            title={`Open “${sessionLabel(session)}”`}
                                            className="min-w-0 flex-1 px-1.5 py-1.5 text-left"
                                        >
                                            <span className={cn('block truncate text-xs font-medium', isActive ? 'text-text' : 'text-dim')}>
                                                {sessionLabel(session)}
                                            </span>
                                            <span className="block truncate text-[10px] text-faint">
                                                {relativeTime(session.timestamp)} · {session.message_count} messages
                                            </span>
                                        </button>
                                        <span className="flex shrink-0 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                                            <IconButton
                                                label="Rename"
                                                size="sm"
                                                onClick={() => { setRenaming(session.id); setDraftTitle(sessionLabel(session)); }}
                                            >
                                                <Pencil size={12} />
                                            </IconButton>
                                            {!isActive && (
                                                <IconButton label="Delete" size="sm" onClick={() => removeSession(session)}>
                                                    <Trash2 size={12} />
                                                </IconButton>
                                            )}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                <div className="mt-2 shrink-0 border-t border-line pt-2">
                    {rail && (
                        <div className="mb-1 flex justify-center">
                            <IconButton
                                label="Expand the sidebar"
                                onClick={() => setCollapsedPreference(false)}
                            >
                                <PanelLeft size={17} />
                            </IconButton>
                        </div>
                    )}
                    <NavLink
                        to="/dashboard/settings"
                        onClick={onCloseMobile}
                        title={rail ? 'Settings' : undefined}
                        className={({ isActive }) => cn(
                            'flex items-center rounded-b2 py-2 text-[13px] font-medium transition-colors',
                            rail ? 'justify-center px-0' : 'gap-3 px-2.5',
                            isActive ? 'bg-fill-3 text-text' : 'text-dim hover:bg-fill-2 hover:text-text',
                        )}
                    >
                        <Settings size={17} className="shrink-0" />
                        {!rail && <span>Settings</span>}
                    </NavLink>
                    {!rail && (
                        <p className="truncate px-2.5 pt-2 font-mono text-[10px] tracking-wider text-faint">
                            {name} Control Room · {VERSION}
                        </p>
                    )}
                </div>
            </Glass>
        </>
    );
}

function sessionLabel(session) {
    return session.title?.trim() || session.preview?.replace(/\.\.\.$/, '') || 'Untitled';
}

function BrandMark({ rail }) {
    return (
        <div className={cn('flex min-w-0 items-center', rail ? 'justify-center' : 'gap-2.5')}>
            <img
                src="/bea.ico"
                alt=""
                width={32}
                height={32}
                className="h-8 w-8 shrink-0 rounded-b2 border border-line object-cover"
            />
            {!rail && (
                <span className="min-w-0">
                    <span className="block truncate font-display text-[13px] font-bold leading-none text-text">{name}</span>
                    <span className="mt-1 block truncate text-[10px] uppercase tracking-widest text-faint">Control room</span>
                </span>
            )}
        </div>
    );
}
