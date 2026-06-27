import React, { useState, useEffect, useRef } from 'react';
import { Activity, Brain, Disc, MessageCircle, Terminal, Cpu, Play, Clock, Zap, Mic, Radio, Archive, LayoutList } from 'lucide-react';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Separator } from '../components/ui/separator';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = 'http://localhost:8000';

// cmd style components
const TerminalLine = ({ event }) => {
    const timeStr = new Date(event.timestamp * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

    let colorClass = "text-zinc-650";
    let bgClass = "bg-transparent";
    let prefix = "INFO";
    let prefixColor = "bg-zinc-100 text-zinc-600 border border-zinc-200/50";

    if (event.category === 'input') { prefix = "INPT"; prefixColor = "bg-blue-50 text-blue-700 border-blue-100"; bgClass = "bg-blue-50/10"; }
    else if (event.category === 'output') { prefix = "OUTP"; prefixColor = "bg-emerald-50 text-emerald-700 border-emerald-100"; bgClass = "bg-emerald-50/10"; }
    else if (event.category === 'thought') { prefix = "THGT"; prefixColor = "bg-purple-50 text-purple-700 border-purple-100"; bgClass = "bg-purple-50/10"; }
    else if (event.category === 'skill') { prefix = "EXEC"; prefixColor = "bg-amber-50 text-amber-700 border-amber-100"; bgClass = "bg-amber-50/10"; }
    else if (event.category === 'error') { prefix = "ERR "; prefixColor = "bg-rose-50 text-rose-700 border-rose-100"; bgClass = "bg-rose-50/20"; }

    return (
        <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className={`font-mono text-xs py-2.5 px-4 border-b border-zinc-100 flex items-start gap-4 ${bgClass} hover:bg-zinc-50/50 transition-colors`}
        >
            <span className="text-zinc-400 select-none text-[10px] pt-0.5 min-w-[50px]">{timeStr}</span>
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded select-none min-w-[40px] text-center ${prefixColor}`}>{prefix}</span>
            <div className="flex-1 break-words text-zinc-800 leading-relaxed">
                <span>{event.message}</span>
                {event.metadata && Object.keys(event.metadata).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                        {Object.entries(event.metadata).map(([k, v]) => (
                            <span key={k} className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-medium bg-zinc-50 text-zinc-500 border border-zinc-200/50">
                                {k}: {String(v)}
                            </span>
                        ))}
                    </div>
                )}
            </div>
        </motion.div>
    );
};

// status hud
const BigStatusCard = ({ icon: Icon, label, value, subtext, active, color }) => {
    const baseColor = {
        green: "text-emerald-700 bg-emerald-50 border-emerald-200 shadow-emerald-500/[0.02]",
        purple: "text-purple-700 bg-purple-50 border-purple-200 shadow-purple-500/[0.02]",
        amber: "text-amber-700 bg-amber-50 border-amber-200 shadow-amber-500/[0.02]",
        blue: "text-blue-700 bg-blue-50 border-blue-200 shadow-blue-500/[0.02]",
        gray: "text-zinc-500 bg-zinc-50 border-zinc-200/60 shadow-none",
    }[color] || "text-zinc-500 bg-zinc-50 border-zinc-200/60";

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: active ? 1.02 : 1 }}
            className={`relative flex-1 min-w-[200px] p-5 rounded-xl border transition-all duration-300 shadow-[0_2px_8px_rgba(0,0,0,0.01)] ${active ? `${baseColor} shadow-sm` : 'bg-zinc-50/50 border-zinc-200/40 text-zinc-400'}`}
        >
            <div className="flex items-start justify-between mb-2">
                <span className="text-[10px] font-bold uppercase tracking-wider opacity-85">{label}</span>
                <Icon className={`w-5 h-5 ${active ? 'opacity-90' : 'opacity-20'}`} />
            </div>
            <div className={`text-xl font-bold tracking-tight ${active ? 'text-zinc-900' : 'text-zinc-400'}`}>
                {value}
            </div>
            {subtext && (
                <div className="text-[9px] font-mono mt-1 opacity-70 truncate">
                    {subtext}
                </div>
            )}
        </motion.div>
    );
};

const HUD = ({ status, lastEvent }) => {
    // derived state
    const isSpeaking = status?.is_speaking || false;
    const isThinking = lastEvent?.category === 'thought' || lastEvent?.category === 'input';

    // active skill
    const activeSkills = status?.active_skills || [];
    const activeSkillText = activeSkills.length > 0 ? activeSkills.join(", ") : "Idle";
    const isActing = activeSkills.length > 0;

    const lastActiveTime = lastEvent ? new Date(lastEvent.timestamp * 1000).toLocaleTimeString() : "--:----";

    return (
        <div className="bg-white border-b border-zinc-200/60 p-6 sticky top-0 z-30">
            <div className="max-w-7xl mx-auto flex flex-col gap-6">

                {/* header title */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <h1 className="text-lg font-bold text-zinc-900 tracking-tight flex items-center gap-2">
                            BRAIN ACTIVITY MONITOR
                            <span className="px-2 py-0.5 rounded-full bg-zinc-55 text-zinc-500 text-[9px] font-mono border border-zinc-200/60">LIVE</span>
                        </h1>
                    </div>
                </div>

                {/* big info cards */}
                <div className="flex flex-wrap gap-4">
                    <BigStatusCard
                        icon={Mic}
                        label="Voice System"
                        value={isSpeaking ? "BROADCASTING" : "STANDBY"}
                        subtext={isSpeaking ? "Audio Output Active" : "Listening..."}
                        active={isSpeaking}
                        color="green"
                    />
                    <BigStatusCard
                        icon={Brain}
                        label="Cognition"
                        value={isThinking ? "PROCESSING" : "IDLE"}
                        subtext={isThinking ? "Generating Response..." : "Waiting for input"}
                        active={isThinking}
                        color="purple"
                    />
                    <BigStatusCard
                        icon={Zap}
                        label="Active Skill"
                        value={activeSkillText}
                        subtext={isActing ? "Executing Action" : "No active task"}
                        active={isActing}
                        color="amber"
                    />
                    <BigStatusCard
                        icon={Clock}
                        label="Last Activity"
                        value={lastActiveTime.split(' ')[0]}
                        subtext={`Late Event: ${lastEvent?.category || 'None'}`}
                        active={true} // Always active/visible
                        color="blue"
                    />
                </div>

            </div>
        </div>
    );
}

export default function BrainActivityPage() {
    const [events, setEvents] = useState([]);
    const [status, setStatus] = useState({});
    const scrollViewportRef = useRef(null);

    const fetchData = async () => {
        try {
            const [eventsRes, statusRes] = await Promise.all([
                fetch(`${API_BASE}/events?limit=100`),
                fetch(`${API_BASE}/status`)
            ]);

            const eventsData = await eventsRes.json();
            const statusData = await statusRes.json();

            // reverse events
            setEvents(eventsData.slice().reverse());
            setStatus(statusData);
        } catch (e) {
            console.error("Failed to fetch activity data:", e);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 1000);
        return () => clearInterval(interval);
    }, []);

    // no auto-scroll

    return (
        <div className="h-screen flex flex-col bg-white font-sans text-zinc-900">

            <HUD status={status} lastEvent={events[0]} />

            <div className="flex-1 overflow-hidden relative flex flex-col max-w-7xl mx-auto w-full mt-4 mb-4 px-6">

                <div className="bg-white rounded-2xl border border-zinc-200/60 flex flex-col flex-1 overflow-hidden shadow-[0_4px_20px_rgba(0,0,0,0.01)]">
                    {/* log header */}
                    <div className="px-4 py-3 bg-zinc-50 border-b border-zinc-200/60 flex justify-between items-center text-[10px] font-mono text-zinc-500">
                        <span className="font-bold flex items-center gap-2 text-zinc-650">
                            <Terminal className="w-3.5 h-3.5" /> EVENT STREAM
                        </span>
                        <span>{events.length} EVENTS LOGGED</span>
                    </div>

                    {/* log content */}
                    <ScrollArea className="flex-1 bg-transparent" viewportRef={scrollViewportRef}>
                        <div className="w-full">
                            {events.length === 0 && (
                                <div className="text-zinc-400 italic p-8 text-center text-xs">Waiting for system events...</div>
                            )}
                            {events.map((event, i) => (
                                <TerminalLine key={event.id || i} event={event} />
                            ))}
                            {/* blinking cursor */}
                            <div className="px-4 py-2 animate-pulse text-zinc-300 font-bold font-mono">_</div>
                        </div>
                    </ScrollArea>
                </div>

            </div>
        </div>
    );
}


