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

    let colorClass = "text-gray-600";
    let bgClass = "bg-transparent";
    let prefix = "INFO";
    let prefixColor = "bg-gray-200 text-gray-700";

    if (event.category === 'input') { prefix = "INPT"; prefixColor = "bg-blue-100 text-blue-700"; bgClass = "bg-blue-50/30"; }
    else if (event.category === 'output') { prefix = "OUTP"; prefixColor = "bg-green-100 text-green-700"; bgClass = "bg-green-50/30"; }
    else if (event.category === 'thought') { prefix = "THGT"; prefixColor = "bg-purple-100 text-purple-700"; bgClass = "bg-purple-50/30"; }
    else if (event.category === 'skill') { prefix = "EXEC"; prefixColor = "bg-amber-100 text-amber-700"; bgClass = "bg-amber-50/30"; }
    else if (event.category === 'error') { prefix = "ERR "; prefixColor = "bg-red-100 text-red-700"; bgClass = "bg-red-50/50"; }

    return (
        <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className={`font-mono text-sm py-2 px-3 border-b border-gray-100 flex items-start gap-4 ${bgClass} hover:bg-gray-50 transition-colors`}
        >
            <span className="text-gray-400 select-none text-xs pt-0.5 min-w-[60px]">{timeStr}</span>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded select-none min-w-[45px] text-center ${prefixColor}`}>{prefix}</span>
            <div className="flex-1 break-words text-gray-800 leading-relaxed">
                <span>{event.message}</span>
                {event.metadata && Object.keys(event.metadata).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                        {Object.entries(event.metadata).map(([k, v]) => (
                            <span key={k} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-200 text-gray-600">
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
        green: "text-green-600 bg-green-50 border-green-200",
        purple: "text-purple-600 bg-purple-50 border-purple-200",
        amber: "text-amber-600 bg-amber-50 border-amber-200",
        blue: "text-blue-600 bg-blue-50 border-blue-200",
        gray: "text-gray-600 bg-gray-50 border-gray-200",
    }[color] || "text-gray-600 bg-gray-50";

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: active ? 1.02 : 1 }}
            whileHover={{ y: -2 }}
            className={`relative flex-1 min-w-[200px] p-5 rounded-xl border-2 transition-all duration-300 shadow-sm ${active ? `${baseColor} shadow-md` : 'bg-white border-gray-100 text-gray-400'}`}
        >
            <div className="flex items-start justify-between mb-2">
                <span className="text-xs font-bold uppercase tracking-widest opacity-70">{label}</span>
                <Icon className={`w-6 h-6 ${active ? 'animate-pulse' : 'opacity-20'}`} />
            </div>
            <div className={`text-2xl font-black tracking-tight ${active ? '' : 'text-gray-700'}`}>
                {value}
            </div>
            {subtext && (
                <div className="text-[10px] font-mono mt-1 opacity-60 truncate">
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
        <div className="bg-white border-b border-gray-200 p-6 sticky top-0 z-30 shadow-sm">
            <div className="max-w-7xl mx-auto flex flex-col gap-6">

                {/* header title */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className={`w-3 h-3 rounded-full ${isSpeaking ? 'bg-green-500 animate-ping' : 'bg-green-500'}`}></div>
                        <h1 className="text-xl font-bold text-gray-900 tracking-tight flex items-center gap-2">
                            BRAIN ACTIVITY MONITOR
                            <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 text-[10px] font-mono border border-gray-200">LIVE</span>
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
        <div className="h-screen flex flex-col bg-gray-50 font-sans text-gray-900">

            <HUD status={status} lastEvent={events[0]} />

            <div className="flex-1 overflow-hidden relative flex flex-col max-w-7xl mx-auto w-full mt-4 mb-4 px-6">

                <div className="bg-white rounded-xl shadow-sm border border-gray-200 flex flex-col flex-1 overflow-hidden">
                    {/* log header */}
                    <div className="px-4 py-3 bg-gray-100/50 border-b border-gray-200 flex justify-between items-center text-xs font-mono text-gray-500">
                        <span className="font-bold flex items-center gap-2">
                            <Terminal className="w-4 h-4" /> EVENT STREAM
                        </span>
                        <span>{events.length} EVENTS LOGGED</span>
                    </div>

                    {/* log content */}
                    <ScrollArea className="flex-1 bg-white" viewportRef={scrollViewportRef}>
                        <div className="w-full">
                            {events.length === 0 && (
                                <div className="text-gray-400 italic p-8 text-center">Waiting for system events...</div>
                            )}
                            {events.map((event, i) => (
                                <TerminalLine key={event.id || i} event={event} />
                            ))}
                            {/* blinking cursor */}
                            <div className="px-4 py-2 animate-pulse text-gray-400 font-bold">_</div>
                        </div>
                    </ScrollArea>
                </div>

            </div>
        </div>
    );
}
