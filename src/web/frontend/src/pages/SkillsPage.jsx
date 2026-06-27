import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '../components/ui/card';
import { Switch } from '../components/ui/switch';
import { Label } from '../components/ui/label';
import { Input } from '../components/ui/input';
import { Separator } from '../components/ui/separator';
import { Button } from '../components/ui/button';
import { Terminal, Settings, Save } from 'lucide-react';
import { motion } from 'framer-motion';
import { useDialog } from '../context/DialogContext';
import MinecraftConsole from '../components/console/MinecraftConsole';

const API_BASE = 'http://localhost:8000';

export default function SkillsPage() {
    const [skills, setSkills] = useState({});
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [config, setConfig] = useState(null);

    // fetch skills
    const fetchSkills = async () => {
        try {
            const res = await fetch(`${API_BASE}/skills`);
            const data = await res.json();
            setSkills(data);
        } catch (e) {
            console.error(e);
        }
    };

    // fetch logs
    const fetchLogs = async () => {
        try {
            const res = await fetch(`${API_BASE}/skills/logs`);
            const data = await res.json();
            // sort logs by timestamp desc
            data.sort((a, b) => b.timestamp - a.timestamp);
            setLogs(data);
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchSkills();
        const interval = setInterval(() => {
            fetchSkills();
            fetchLogs();
        }, 2000); // poll every 2s
        return () => clearInterval(interval);
    }, []);

    // fetch global config

    useEffect(() => {
        const fetchGlobalConfig = async () => {
            try {
                const res = await fetch(`${API_BASE}/config`);
                const data = await res.json();
                setConfig(data);
            } catch (e) {
                console.error(e);
            } finally {
                setLoading(false);
            }
        };
        fetchGlobalConfig();
    }, []);

    const toggleSkill = async (name, state) => {
        try {
            await fetch(`${API_BASE}/skills/${name}/toggle?enable=${state}`, { method: 'POST' });
            fetchSkills();
            setConfig(prev => ({
                ...prev,
                skills: {
                    ...prev.skills,
                    [name]: { ...prev.skills[name], enabled: state }
                }
            }));
        } catch (e) {
            console.error(e);
        }
    };

    const { alert } = useDialog();

    const saveConfig = async () => {
        if (!config) return;
        try {
            await fetch(`${API_BASE}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            });
            await alert("Settings Saved!", "Success");
        } catch (e) {
            console.error(e);
        }
    };

    const updateSkillConfig = (skillName, key, value) => {
        setConfig(prev => ({
            ...prev,
            skills: {
                ...prev.skills,
                [skillName]: { ...prev.skills[skillName], [key]: value }
            }
        }));
    };

    const [consoleOpen, setConsoleOpen] = useState(false);

    if (loading) return <div className="p-10">Loading Skills...</div>;

    return (
        <div className="flex h-screen bg-transparent text-zinc-900">
            {consoleOpen && (
                <MinecraftConsole
                    serverUrl={config?.skills?.minecraft?.server_url || "ws://localhost:8080"}
                    onClose={() => setConsoleOpen(false)}
                />
            )}
            {/* main content */}
            <div className="w-full p-8 overflow-y-auto">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="max-w-6xl"
                >
                    <h1 className="text-2xl font-bold text-zinc-900 mb-8 tracking-tight">Skills & Behaviors</h1>

                    <motion.div
                        initial="hidden"
                        animate="visible"
                        variants={{
                            visible: { transition: { staggerChildren: 0.1 } }
                        }}
                        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                    >
                        {Object.entries(config?.skills || {}).map(([skillName, skillConfig]) => {
                            const runtimeStatus = skills[skillName] || {};
                            return (
                                <motion.div
                                    key={skillName}
                                    variants={{
                                        hidden: { opacity: 0, y: 20 },
                                        visible: { opacity: 1, y: 0 }
                                    }}
                                >
                                    <Card className="bg-white border-zinc-200/80 shadow-sm">
                                        <CardHeader className="pb-3">
                                            <div className="flex justify-between items-center">
                                                <div>
                                                    <CardTitle className="capitalize text-lg text-zinc-900">{skillName}</CardTitle>
                                                    <CardDescription className="text-zinc-400 text-xs mt-1">
                                                        Status: {runtimeStatus.active ? <span className="text-emerald-600 font-semibold">Active</span> : <span className="text-zinc-400">Idle</span>}
                                                    </CardDescription>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <Switch
                                                        checked={skillConfig.enabled}
                                                        onCheckedChange={(checked) => toggleSkill(skillName, checked)}
                                                    />
                                                    <span className={`text-xs font-medium ${skillConfig.enabled ? "text-zinc-900" : "text-zinc-400"}`}>{skillConfig.enabled ? "ON" : "OFF"}</span>
                                                </div>
                                            </div>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                            {/* specific fields for monologue */}
                                            {skillName === 'monologue' && (
                                                <>
                                                    <div className="grid grid-cols-1 gap-2">
                                                        <Label className="text-xs text-zinc-500">Trigger Interval (seconds)</Label>
                                                        <Input
                                                            type="number"
                                                            value={skillConfig.interval_seconds}
                                                            onChange={(e) => updateSkillConfig(skillName, 'interval_seconds', parseInt(e.target.value))}
                                                            className="bg-white border-zinc-200 text-zinc-900 focus:border-zinc-400 focus:ring-zinc-100"
                                                        />
                                                    </div>
                                                    <div className="grid grid-cols-1 gap-2">
                                                        <Label className="text-xs text-zinc-500">Instruction / System Prompt</Label>
                                                        <Input
                                                            value={skillConfig.prompt_instructions}
                                                            onChange={(e) => updateSkillConfig(skillName, 'prompt_instructions', e.target.value)}
                                                            className="bg-white border-zinc-200 text-zinc-900 focus:border-zinc-400 focus:ring-zinc-100"
                                                        />
                                                    </div>
                                                </>
                                            )}
                                            {skillName === 'memory' && (
                                                <div className="space-y-4">
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs text-zinc-500">ChromaDB Path</Label>
                                                        <Input
                                                            value={skillConfig.chroma_path || 'data/memory_db'}
                                                            onChange={(e) => updateSkillConfig(skillName, 'chroma_path', e.target.value)}
                                                            className="bg-white border-zinc-200 text-zinc-900 focus:border-zinc-400 focus:ring-zinc-100"
                                                        />
                                                    </div>

                                                    <Button
                                                        size="sm"
                                                        className="w-full mt-2 bg-black text-white hover:bg-zinc-800 cursor-pointer text-xs font-semibold"
                                                        onClick={async () => {
                                                            const btn = document.getElementById("save-mem-btn");
                                                            if (btn) btn.disabled = true;
                                                            try {
                                                                const res = await fetch(`${API_BASE}/memory/save`, { method: 'POST' });
                                                                const data = await res.json();
                                                                if (data.status === 'success') alert("Memory Saved", "Session saved to long-term memory.");
                                                                else alert("Error", data.message);
                                                            } catch (e) {
                                                                console.error(e);
                                                                alert("Error", "Failed to contact server.");
                                                            } finally {
                                                                if (btn) btn.disabled = false;
                                                            }
                                                        }}
                                                        id="save-mem-btn"
                                                    >
                                                        <Save className="w-3.5 h-3.5 mr-2" />
                                                        Save Memory Now
                                                    </Button>
                                                </div>
                                            )}
                                            {skillName === 'minecraft' && (
                                                <div className="space-y-4">
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs text-zinc-500">Server URL</Label>
                                                        <Input
                                                            value={skillConfig.server_url || ''}
                                                            onChange={(e) => updateSkillConfig(skillName, 'server_url', e.target.value)}
                                                            placeholder="ws://localhost:8080"
                                                            className="bg-white border-zinc-200 text-zinc-900 focus:border-zinc-400 focus:ring-zinc-100"
                                                        />
                                                    </div>
                                                    <div className="flex items-center justify-between border border-zinc-150 rounded-md p-2 bg-zinc-50/50">
                                                        <Label className="text-xs text-zinc-500">Auto Speak Thoughts</Label>
                                                        <Switch
                                                            checked={skillConfig.auto_speak_thoughts || false}
                                                            onCheckedChange={(checked) => updateSkillConfig(skillName, 'auto_speak_thoughts', checked)}
                                                        />
                                                    </div>
                                                </div>
                                            )}
                                            {skillName === 'discord' && (
                                                <div className="space-y-4">
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs text-zinc-500">Bot Token</Label>
                                                        <Input
                                                            type="password"
                                                            value={skillConfig.token || ''}
                                                            onChange={(e) => updateSkillConfig(skillName, 'token', e.target.value)}
                                                            placeholder="Enter Discord Bot Token"
                                                            className="bg-white border-zinc-200 text-zinc-900 focus:border-zinc-400 focus:ring-zinc-100"
                                                        />
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs text-zinc-500">Target Channel ID</Label>
                                                        <Input
                                                            value={skillConfig.target_channel || ''}
                                                            onChange={(e) => updateSkillConfig(skillName, 'target_channel', e.target.value)}
                                                            placeholder="123456789012345678"
                                                            className="bg-white border-zinc-200 text-zinc-900 focus:border-zinc-400 focus:ring-zinc-100"
                                                        />
                                                    </div>
                                                    <p className="text-[11px] text-zinc-400 mt-1.5">
                                                        Enable the skill and restart the brain to start the bot process.
                                                    </p>
                                                </div>
                                            )}
                                            <div className="pt-2 flex justify-end gap-2">
                                                {skillName === 'minecraft' && (
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="text-zinc-500 hover:text-zinc-950 hover:bg-zinc-100 cursor-pointer"
                                                        onClick={() => setConsoleOpen(true)}
                                                    >
                                                        <Settings className="w-4 h-4 mr-2" /> Console
                                                    </Button>
                                                )}
                                                <Button size="sm" variant="outline" className="cursor-pointer border-zinc-200 hover:bg-zinc-50" onClick={saveConfig}>Save Settings</Button>
                                            </div>
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            );
                        })}
                    </motion.div>
                </motion.div>
            </div>
        </div>
    );
}
