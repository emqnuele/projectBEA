import React, { useState, useEffect } from 'react';
import { MessageSquare, Settings, ChevronDown, ChevronRight, Server, Mic, Volume2, Video, Type, User, Plus, BrainCircuit, Activity, Box } from 'lucide-react';
import { motion } from 'framer-motion';
import { useDialog } from '../context/DialogContext';

export default function Sidebar({ view, setView, configCategory, setConfigCategory, onSessionChange }) {
    const [isConfigOpen, setIsConfigOpen] = useState(true);
    const dialog = useDialog();

    const configItems = [
        { id: 'LLM', label: 'Model', icon: Server },
        { id: 'STT', label: 'Speech to Text', icon: Mic },
        { id: 'TTS', label: 'Voice', icon: Volume2 },
        { id: 'OBS', label: 'Stream', icon: Video },
        { id: 'Typing', label: 'Typing', icon: Type },
        { id: 'Avatar', label: 'Avatar', icon: User },
        { id: 'General', label: 'General', icon: BrainCircuit },
        { id: 'Minecraft', label: 'Minecraft', icon: Box },
        { id: 'Discord', label: 'Discord', icon: BrainCircuit },
    ];

    const [sessions, setSessions] = useState([]);
    const [loadingSessions, setLoadingSessions] = useState(false);

    useEffect(() => {
        fetchSessions();
    }, []);

    const fetchSessions = async () => {
        setLoadingSessions(true);
        try {
            const res = await fetch('http://localhost:8000/sessions');
            if (res.ok) {
                const data = await res.json();
                setSessions(data);
            }
        } catch (e) {
            console.error("Failed to fetch sessions", e);
        } finally {
            setLoadingSessions(false);
        }
    };

    const handleNewChat = async () => {
        const confirmed = await dialog.confirm("Start a new chat? Current context will be cleared.", "Start New Chat");
        if (!confirmed) return;

        try {
            const res = await fetch('http://localhost:8000/sessions', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                fetchSessions();
                if (setView) setView('chat');
                if (onSessionChange) onSessionChange();
            }
        } catch (e) {
            console.error("Failed to create session", e);
        }
    };

    const handleSessionClick = async (sessionId) => {
        try {
            const res = await fetch(`http://localhost:8000/sessions/${sessionId}/activate`, { method: 'POST' });
            if (res.ok) {
                if (setView) setView('chat');
                if (onSessionChange) onSessionChange();
            }
        } catch (e) {
            console.error("Failed to activate session", e);
        }
    };

    const handleConfigClick = () => {
        if (view !== 'config') {
            setView('config');
            setIsConfigOpen(true);
        } else {
            setIsConfigOpen(!isConfigOpen);
        }
    };

    return (
        <div className="w-[240px] h-screen bg-zinc-50/80 backdrop-blur-md border-r border-zinc-200/50 flex flex-col py-6 transition-all duration-300 select-none">
            {/* logo */}
            <div className="flex items-center px-6 mb-8 mt-2">
                <div className="w-8 h-8 rounded-lg bg-black text-white flex items-center justify-center font-bold text-sm shadow-sm">
                    PB
                </div>
                <div className="ml-3 flex flex-col">
                    <span className="font-bold text-sm tracking-tight text-zinc-900 leading-none">
                        Project<span className="text-zinc-500 font-medium">Bea</span>
                    </span>
                    <span className="text-[10px] font-medium text-zinc-400 mt-1 uppercase tracking-widest">
                        Neural Engine
                    </span>
                </div>
            </div>

            <div className="flex-1 min-h-0 flex flex-col px-3 overflow-hidden">
                {/* new chat button */}
                <motion.button
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    onClick={handleNewChat}
                    className="w-full flex items-center px-4 py-2.5 rounded-xl bg-black text-white hover:bg-zinc-800 transition-colors shadow-sm mb-6 cursor-pointer"
                >
                    <Plus size={18} />
                    <span className="ml-3 text-sm font-semibold">Initialize Chat</span>
                </motion.button>

                {/* nav items */}
                <div className="space-y-1">
                    <button
                        onClick={() => setView('chat')}
                        className={`w-full flex items-center px-3 py-2 rounded-md transition-colors group cursor-pointer
                            ${view === 'chat'
                                ? 'bg-zinc-150 text-zinc-900 border border-zinc-200/50 shadow-sm'
                                : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900 border border-transparent'
                            }`}
                    >
                        <MessageSquare size={18} className={view === 'chat' ? 'text-zinc-900' : 'text-zinc-400'} />
                        <span className="ml-3 text-sm font-medium">Chat</span>
                    </button>

                    <button
                        onClick={() => setView('activity')}
                        className={`w-full flex items-center px-3 py-2 rounded-md transition-colors group cursor-pointer
                            ${view === 'activity'
                                ? 'bg-zinc-150 text-zinc-900 border border-zinc-200/50 shadow-sm'
                                : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900 border border-transparent'
                            }`}
                    >
                        <Activity size={18} className={view === 'activity' ? 'text-zinc-900' : 'text-zinc-400'} />
                        <span className="ml-3 text-sm font-medium">Activity</span>
                    </button>

                    <button
                        onClick={() => setView('skills')}
                        className={`w-full flex items-center px-3 py-2 rounded-md transition-colors group cursor-pointer
                            ${view === 'skills'
                                ? 'bg-zinc-150 text-zinc-900 border border-zinc-200/50 shadow-sm'
                                : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900 border border-transparent'
                            }`}
                    >
                        <BrainCircuit size={18} className={view === 'skills' ? 'text-zinc-900' : 'text-zinc-400'} />
                        <span className="ml-3 text-sm font-medium">Skills</span>
                    </button>

                    {/* config group */}
                    <div className="pt-1">
                        <button
                            onClick={handleConfigClick}
                            className={`w-full flex items-center justify-between px-3 py-2 rounded-md transition-colors group cursor-pointer
                                ${view === 'config' && !isConfigOpen
                                    ? 'bg-zinc-150 text-zinc-900 border border-zinc-200/50 shadow-sm'
                                    : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900 border border-transparent'
                                }`}
                        >
                            <div className="flex items-center">
                                <Settings size={18} className={view === 'config' ? 'text-zinc-900' : 'text-zinc-400'} />
                                <span className="ml-3 text-sm font-medium">Settings</span>
                            </div>
                            {isConfigOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </button>

                        {/* submenu */}
                        {isConfigOpen && (
                            <div className="mt-1 ml-4 pl-3 border-l border-zinc-250 space-y-0.5 max-h-[200px] overflow-y-auto">
                                {configItems.map(item => {
                                    const isActive = view === 'config' && configCategory === item.id;
                                    return (
                                        <button
                                            key={item.id}
                                            onClick={() => {
                                                if (view !== 'config') setView('config');
                                                setConfigCategory(item.id);
                                            }}
                                            className={`w-full flex items-center px-3 py-1.5 rounded-md text-xs transition-colors cursor-pointer
                                                ${isActive
                                                    ? 'text-zinc-900 font-semibold bg-zinc-150 border border-zinc-200/30'
                                                    : 'text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100/50 border border-transparent'
                                                }`}
                                        >
                                            <item.icon size={12} className="mr-2 opacity-70" />
                                            <span>{item.label}</span>
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>

                {/* history section */}
                <div className="pt-6 flex-1 min-h-0 flex flex-col overflow-hidden">
                    <div className="px-3 text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                        Recent Chats
                    </div>
                    <div className="space-y-1 overflow-y-auto pr-1 flex-1 min-h-0">
                        {loadingSessions ? (
                            <div className="px-3 text-xs text-zinc-400 italic">Loading...</div>
                        ) : sessions.length === 0 ? (
                            <div className="px-3 text-xs text-zinc-400 italic">No history yet</div>
                        ) : (
                            sessions.map(session => (
                                <button
                                    key={session.id}
                                    onClick={() => handleSessionClick(session.id)}
                                    className="w-full text-left px-3 py-2 rounded-md text-xs text-zinc-600 hover:bg-zinc-150/50 hover:text-zinc-900 border border-transparent hover:border-zinc-200/30 transition-colors truncate cursor-pointer"
                                    title={session.preview}
                                >
                                    <div className="font-medium text-zinc-900 truncate">{new Date(session.timestamp).toLocaleDateString()}</div>
                                    <div className="truncate opacity-75 text-zinc-500">{session.preview || "Empty session"}</div>
                                </button>
                            ))
                        )}
                    </div>
                </div>
            </div>

            {/* footer */}
            <div className="px-6 pt-4 border-t border-zinc-200/40 text-[10px] text-zinc-400 tracking-wider">
                v1.0.0
            </div>
        </div>
    );
}


