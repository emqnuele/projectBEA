import React, { useState, useEffect } from 'react';
import { MessageSquare, Settings, ChevronDown, ChevronRight, Server, Mic, Video, Type, User, Plus, BrainCircuit, Activity, Box } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useDialog } from '../context/DialogContext';

export default function Sidebar({ view, setView, configCategory, setConfigCategory, onSessionChange }) {
    const [isConfigOpen, setIsConfigOpen] = useState(true);
    const dialog = useDialog();

    const configItems = [
        { id: 'LLM', label: 'Model', icon: Server },
        { id: 'TTS', label: 'Voice', icon: Mic },
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
        <div className="w-[240px] h-screen bg-zinc-50 border-r border-zinc-200 flex flex-col py-6 transition-all duration-300">
            {/* logo */}
            <div className="flex items-center px-6 mb-8 mt-2">
                <motion.div
                    whileHover={{ scale: 1.05, rotate: 5 }}
                    className="w-8 h-8 rounded-lg bg-black text-white flex items-center justify-center font-bold text-sm shadow-lg shadow-zinc-200"
                >
                    PB
                </motion.div>
                <div className="ml-3 flex flex-col">
                    <span className="font-bold text-sm tracking-tight text-zinc-900 leading-none">
                        Project<span className="text-blue-500">Bea</span>
                    </span>
                    <span className="text-[10px] font-medium text-zinc-400 mt-1 uppercase tracking-widest">
                        Neural Engine
                    </span>
                </div>
            </div>

            <nav className="flex-1 space-y-1 px-3">
                {/* new chat button */}
                <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={handleNewChat}
                    className="w-full flex items-center px-4 py-2.5 rounded-xl bg-black text-white hover:bg-zinc-800 transition-colors shadow-md shadow-zinc-200 mb-6"
                >
                    <Plus size={18} />
                    <span className="ml-3 text-sm font-semibold">Initialize Chat</span>
                </motion.button>

                {/* chat item */}
                <button
                    onClick={() => setView('chat')}
                    className={`w-full flex items-center px-3 py-2 rounded-md transition-colors group
            ${view === 'chat'
                            ? 'bg-white text-zinc-900 shadow-sm ring-1 ring-zinc-200'
                            : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900'
                        }`}
                >
                    <MessageSquare size={18} className={view === 'chat' ? 'text-black' : 'text-zinc-400'} />
                    <span className="ml-3 text-sm font-medium">Chat</span>
                </button>

                {/* activity item */}
                <button
                    onClick={() => setView('activity')}
                    className={`w-full flex items-center px-3 py-2 rounded-md transition-colors group mt-1
            ${view === 'activity'
                            ? 'bg-white text-zinc-900 shadow-sm ring-1 ring-zinc-200'
                            : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900'
                        }`}
                >
                    <Activity size={18} className={view === 'activity' ? 'text-purple-500' : 'text-zinc-400'} />
                    <span className="ml-3 text-sm font-medium">Activity</span>
                </button>

                {/* skills item */}
                <button
                    onClick={() => setView('skills')}
                    className={`w-full flex items-center px-3 py-2 rounded-md transition-colors group mt-1
            ${view === 'skills'
                            ? 'bg-white text-zinc-900 shadow-sm ring-1 ring-zinc-200'
                            : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900'
                        }`}
                >
                    <BrainCircuit size={18} className={view === 'skills' ? 'text-black' : 'text-zinc-400'} />
                    <span className="ml-3 text-sm font-medium">Skills</span>
                </button>

                {/* config group */}
                <div className="pt-2">
                    <button
                        onClick={handleConfigClick}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded-md transition-colors group
                ${view === 'config' && !isConfigOpen
                                ? 'bg-white text-zinc-900 shadow-sm ring-1 ring-zinc-200'
                                : 'text-zinc-500 hover:bg-zinc-100/50 hover:text-zinc-900'
                            }`}
                    >
                        <div className="flex items-center">
                            <Settings size={18} className={view === 'config' ? 'text-black' : 'text-zinc-400'} />
                            <span className="ml-3 text-sm font-medium">Settings</span>
                        </div>
                        {isConfigOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>

                    {/* submenu */}
                    {isConfigOpen && (
                        <div className="mt-1 ml-4 pl-3 border-l border-zinc-200 space-y-0.5">
                            {configItems.map(item => {
                                const isActive = view === 'config' && configCategory === item.id;
                                return (
                                    <button
                                        key={item.id}
                                        onClick={() => {
                                            if (view !== 'config') setView('config');
                                            setConfigCategory(item.id);
                                        }}
                                        className={`w-full flex items-center px-3 py-1.5 rounded-md text-sm transition-colors
                                ${isActive
                                                ? 'text-zinc-900 font-medium bg-zinc-100'
                                                : 'text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100/50'
                                            }`}
                                    >
                                        <item.icon size={14} className="mr-2 opacity-70" />
                                        <span>{item.label}</span>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* history section */}
                <div className="pt-6">
                    <div className="px-3 text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                        Recent Chats
                    </div>
                    <div className="space-y-1 max-h-[300px] overflow-y-auto pr-1">
                        {loadingSessions ? (
                            <div className="px-3 text-xs text-zinc-400 italic">Loading...</div>
                        ) : sessions.length === 0 ? (
                            <div className="px-3 text-xs text-zinc-400 italic">No history yet</div>
                        ) : (
                            sessions.map(session => (
                                <button
                                    key={session.id}
                                    onClick={() => handleSessionClick(session.id)}
                                    className="w-full text-left px-3 py-2 rounded-md text-xs text-zinc-600 hover:bg-zinc-100 transition-colors truncate"
                                    title={session.preview}
                                >
                                    <div className="font-medium text-zinc-900 truncate">{new Date(session.timestamp).toLocaleDateString()}</div>
                                    <div className="truncate opacity-70">{session.preview || "Empty session"}</div>
                                </button>
                            ))
                        )}
                    </div>
                </div>
            </nav>

            {/* footer */}
            <div className="px-6 pb-2">
                <div className="flex items-center gap-2 text-zinc-400">
                    <div className="w-2 h-2 rounded-full bg-green-500"></div>
                    <span className="text-xs font-medium">System Online</span>
                </div>
            </div>
        </div>
    );
}
