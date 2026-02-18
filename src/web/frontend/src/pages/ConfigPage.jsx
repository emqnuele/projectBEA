import React, { useState, useEffect } from 'react';
import { Save, Plus, Trash2, Check, X, RefreshCw, Key, Image as ImageIcon, Box, Edit } from 'lucide-react';
import { useDialog } from '../context/DialogContext';
import SystemPromptModal from '../components/config/SystemPromptModal';

const API_BASE = 'http://localhost:8000';

export default function ConfigPage({ activeCategory }) {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isPromptModalOpen, setIsPromptModalOpen] = useState(false);
    const dialog = useDialog();

    useEffect(() => {
        fetchConfig()
    }, [])

    const fetchConfig = async () => {
        try {
            const res = await fetch(`${API_BASE}/config`)
            const data = await res.json()
            setConfig(data)
        } catch (e) {
            console.error(e)
        } finally {
            setLoading(false)
        }
    }

    const handleSave = async () => {
        setIsSaving(true);
        try {
            const res = await fetch(`${API_BASE}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            })
            const data = await res.json()

            if (res.ok) {
                if (data.restart_required) {
                    dialog.alert('Configuration saved. Please RESTART the application server to apply the new TTS provider.', 'Restart Required');
                } else {
                    dialog.alert('Configuration saved successfully.', 'Saved');
                }
            } else {
                dialog.alert('There was an error saving the configuration.', 'Error');
            }
        } catch (e) {
            dialog.alert(e.message, 'Error');
        } finally {
            setIsSaving(false);
        }
    }

    const updateField = (key, value) => {
        setConfig(prev => ({ ...prev, [key]: value }))
    }

    const updateAvatarMap = (mood, state, value) => {
        setConfig(prev => ({
            ...prev,
            avatar_map: {
                ...prev.avatar_map,
                [mood]: {
                    ...prev.avatar_map[mood],
                    [state]: value
                }
            }
        }))
    }

    const updateSkillField = (skillName, key, value) => {
        setConfig(prev => ({
            ...prev,
            skills: {
                ...prev.skills,
                [skillName]: {
                    ...prev.skills[skillName],
                    [key]: value
                }
            }
        }))
    }

    if (loading || !config) return <div className="p-12 text-center text-sm text-zinc-500">Loading...</div>

    return (
        <div className="h-full flex flex-col max-w-4xl mx-auto animate-in">
            {/* header */}
            <div className="px-8 py-8 flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight text-zinc-900">{activeCategory}</h2>
                    <p className="text-sm text-zinc-500 mt-1">Configure your settings.</p>
                </div>
                <button
                    onClick={handleSave}
                    disabled={isSaving}
                    className="flex items-center px-5 py-2.5 bg-zinc-900 text-white text-sm font-medium rounded-md hover:bg-zinc-800 transition-colors disabled:opacity-50 shadow-sm"
                >
                    <Save size={16} className="mr-2" />
                    {isSaving ? 'Saving...' : 'Save Changes'}
                </button>
            </div>

            {/* content */}
            <div className="flex-1 overflow-y-auto px-8 pb-8">
                <div className="space-y-8">

                    {activeCategory === 'LLM' && (
                        <div className="space-y-8">
                            <section>
                                <label className="text-sm font-medium text-zinc-900 block mb-4">Provider Selection</label>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {['gemini', 'glm', 'openai', 'groq'].map(p => (
                                        <label key={p} className={`cursor-pointer border rounded-xl p-4 transition-all relative
                                            ${config.llm_provider === p
                                                ? 'border-zinc-900 bg-zinc-50 shadow-sm ring-1 ring-zinc-900'
                                                : 'border-zinc-200 hover:border-zinc-300'
                                            }`}>
                                            <input type="radio"
                                                className="hidden"
                                                checked={config.llm_provider === p}
                                                onChange={() => updateField('llm_provider', p)}
                                            />
                                            <div className="font-semibold capitalize text-sm">{p}</div>
                                            <p className="text-xs text-zinc-500 mt-1">
                                                {p === 'gemini' ? 'Google DeepMind multimodal model.' : p === 'glm' ? 'Zhipu AI advanced language model.' : p === 'openai' ? 'OpenAI GPT-4o advanced model.' : 'Groq Fast Inference.'}
                                            </p>
                                        </label>
                                    ))}
                                </div>
                            </section>

                            {config.llm_provider === 'gemini' && (
                                <section className="space-y-4">
                                    <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Gemini Configuration</label>
                                    <div className="grid gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">API Key</label>
                                            <input
                                                type="password"
                                                value={config.gemini_key || ''}
                                                onChange={(e) => updateField('gemini_key', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                                placeholder="AIza..."
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Model Name</label>
                                            <input
                                                type="text"
                                                value={config.gemini_model || ''}
                                                onChange={(e) => updateField('gemini_model', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                            />
                                        </div>
                                    </div>
                                </section>
                            )}

                            {config.llm_provider === 'glm' && (
                                <section className="space-y-4">
                                    <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">GLM Configuration</label>
                                    <div className="grid gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">API Key</label>
                                            <input
                                                type="password"
                                                value={config.glm_key || ''}
                                                onChange={(e) => updateField('glm_key', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Model Name</label>
                                            <input
                                                type="text"
                                                value={config.glm_model || ''}
                                                onChange={(e) => updateField('glm_model', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                            />
                                        </div>
                                    </div>
                                </section>
                            )}

                            {config.llm_provider === 'openai' && (
                                <section className="space-y-4">
                                    <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">OpenAI Configuration</label>
                                    <div className="grid gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">API Key</label>
                                            <input
                                                type="password"
                                                value={config.openai_key || ''}
                                                onChange={(e) => updateField('openai_key', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Model Name</label>
                                            <input
                                                type="text"
                                                value={config.openai_model || ''}
                                                onChange={(e) => updateField('openai_model', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                            />
                                        </div>
                                    </div>
                                </section>
                            )}

                            {config.llm_provider === 'groq' && (
                                <section className="space-y-4">
                                    <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Groq Configuration</label>
                                    <div className="grid gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">API Key</label>
                                            <input
                                                type="password"
                                                value={config.groq_key || ''}
                                                onChange={(e) => updateField('groq_key', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Model Name</label>
                                            <input
                                                type="text"
                                                value={config.groq_model || ''}
                                                onChange={(e) => updateField('groq_model', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 focus:border-zinc-900 outline-none transition-all"
                                            />
                                        </div>
                                    </div>
                                </section>
                            )}
                        </div>
                    )}

                    {activeCategory === 'TTS' && (
                        <div className="space-y-8">
                            <section>
                                <label className="text-sm font-medium text-zinc-900 block mb-4">TTS Provider</label>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    {['edge', 'orpheus', 'kokoro'].map(p => (
                                        <label key={p} className={`cursor-pointer border rounded-xl p-4 transition-all relative
                                            ${config.tts_provider === p
                                                ? 'border-zinc-900 bg-zinc-50 shadow-sm ring-1 ring-zinc-900'
                                                : 'border-zinc-200 hover:border-zinc-300'
                                            }`}>
                                            <input type="radio"
                                                className="hidden"
                                                checked={config.tts_provider === p}
                                                onChange={() => updateField('tts_provider', p)}
                                            />
                                            <div className="font-semibold capitalize text-sm">{p} TTS</div>
                                            <p className="text-xs text-zinc-500 mt-1">
                                                {p === 'edge' ? 'Microsoft Edge Online (Fast & Free).' : p === 'kokoro' ? 'Kokoro ONNX (Local, Fast, Best).' : 'Orpheus (Baseten Hosted).'}
                                            </p>
                                        </label>
                                    ))}
                                </div>
                            </section>

                            <section className="space-y-4">
                                <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Voice Settings</label>
                                {config.tts_provider === 'edge' && (
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-1.5 col-span-2">
                                            <label className="text-xs font-medium text-zinc-500">Voice ID</label>
                                            <input
                                                value={config.tts_voice || ''}
                                                onChange={(e) => updateField('tts_voice', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                                placeholder="e.g. en-US-AriaNeural"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Pitch (e.g. +5Hz)</label>
                                            <input
                                                value={config.tts_pitch || ''}
                                                onChange={(e) => updateField('tts_pitch', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                                placeholder="+0Hz"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Rate (e.g. +10%)</label>
                                            <input
                                                value={config.tts_rate || ''}
                                                onChange={(e) => updateField('tts_rate', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                                placeholder="+0%"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Volume (e.g. +33%)</label>
                                            <input
                                                value={config.tts_volume || ''}
                                                onChange={(e) => updateField('tts_volume', e.target.value)}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                                placeholder="+0%"
                                            />
                                        </div>
                                    </div>
                                )}
                                {config.tts_provider === 'coqui' && (
                                    <div className="p-4 bg-yellow-50 text-yellow-800 rounded text-sm">
                                        Coqui TTS has been removed to optimize dependencies. Please select another provider.
                                    </div>
                                )}
                                {config.tts_provider === 'orpheus' && (
                                    <div className="grid gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">API Key</label>
                                            <input type="password" value={config.orpheus_key || ''} onChange={(e) => updateField('orpheus_key', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" placeholder="Orpheus API Key" />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Endpoint</label>
                                            <input value={config.orpheus_endpoint || ''} onChange={(e) => updateField('orpheus_endpoint', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" placeholder="https://model-..." />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Voice</label>
                                            <input value={config.orpheus_voice || ''} onChange={(e) => updateField('orpheus_voice', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" placeholder="tara" />
                                        </div>
                                    </div>
                                )}
                                {config.tts_provider === 'kokoro' && (
                                    <div className="grid gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Voice</label>
                                            <input value={config.kokoro_voice || ''} onChange={(e) => updateField('kokoro_voice', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" placeholder="e.g. af_bella, af_sky, am_adam..." />
                                            <p className="text-[10px] text-zinc-400">Available: af_bella, af_sarah, af_nicole, af_sky, am_adam, am_michael, bm_lewis, bm_george...</p>
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Speed</label>
                                            <input type="number" step="0.1" value={config.kokoro_speed || 1.0} onChange={(e) => updateField('kokoro_speed', parseFloat(e.target.value))} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Language</label>
                                            <input value={config.kokoro_lang || 'en-us'} onChange={(e) => updateField('kokoro_lang', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                                        </div>
                                    </div>
                                )}
                                <div className="pt-4">
                                    <label className="text-xs font-medium text-zinc-500">Output Device ID</label>
                                    <input
                                        type="number"
                                        value={config.audio_device_id || 0}
                                        onChange={(e) => updateField('audio_device_id', parseInt(e.target.value))}
                                        className="w-24 ml-4 border border-zinc-200 rounded-md px-2 py-1 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                    />
                                    <span className="ml-2 text-xs text-zinc-400">(Default: 0, VB-Cable often 24+)</span>
                                </div>
                            </section>
                        </div>
                    )}

                    {activeCategory === 'OBS' && (
                        <div className="space-y-6">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-1.5">
                                    <label className="text-xs font-medium text-zinc-500">Host</label>
                                    <input value={config.obs_host} onChange={(e) => updateField('obs_host', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-xs font-medium text-zinc-500">Port</label>
                                    <input type="number" value={config.obs_port} onChange={(e) => updateField('obs_port', parseInt(e.target.value))} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                                </div>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-xs font-medium text-zinc-500">Password</label>
                                <input type="password" value={config.obs_password} onChange={(e) => updateField('obs_password', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                            </div>
                            <div className="pt-4 border-t border-zinc-100 space-y-4">
                                <div className="space-y-4">
                                    <label className="text-sm font-medium text-zinc-900 block">OBS Source Type</label>
                                    <div className="grid grid-cols-2 gap-4">
                                        {['image', 'media'].map(type => (
                                            <label key={type} className={`cursor-pointer border rounded-xl p-4 transition-all relative
                                                ${config.obs_source_type === type
                                                    ? 'border-zinc-900 bg-zinc-50 shadow-sm ring-1 ring-zinc-900'
                                                    : 'border-zinc-200 hover:border-zinc-300'
                                                }`}>
                                                <input type="radio"
                                                    className="hidden"
                                                    checked={config.obs_source_type === type}
                                                    onChange={() => updateField('obs_source_type', type)}
                                                />
                                                <div className="font-semibold capitalize text-sm">{type} Source</div>
                                                <p className="text-xs text-zinc-500 mt-1">
                                                    {type === 'image' ? 'Static PNG images.' : 'Video/Media files.'}
                                                </p>
                                            </label>
                                        ))}
                                    </div>
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-xs font-medium text-zinc-500">Avatar Source Name</label>
                                    <input value={config.obs_avatar_source} onChange={(e) => updateField('obs_avatar_source', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-xs font-medium text-zinc-500">Text Source Name</label>
                                    <input value={config.obs_text_source} onChange={(e) => updateField('obs_text_source', e.target.value)} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                                </div>
                            </div>
                        </div>
                    )}

                    {activeCategory === 'Typing' && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-1.5">
                                <label className="text-xs font-medium text-zinc-500">Line Width</label>
                                <input type="number" value={config.text_line_width} onChange={(e) => updateField('text_line_width', parseInt(e.target.value))} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-xs font-medium text-zinc-500">Font Size</label>
                                <input type="number" value={config.text_font_size} onChange={(e) => updateField('text_font_size', parseInt(e.target.value))} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-xs font-medium text-zinc-500">Typing Delay (seconds)</label>
                                <input type="number" step="0.01" value={config.typing_delay} onChange={(e) => updateField('typing_delay', parseFloat(e.target.value))} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-xs font-medium text-zinc-500">Min Duration (seconds)</label>
                                <input type="number" step="0.1" value={config.text_min_duration || 2.0} onChange={(e) => updateField('text_min_duration', parseFloat(e.target.value))} className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none" />
                            </div>
                        </div>
                    )}



                    {activeCategory === 'Avatar' && (
                        <div className="space-y-8">
                            <section className="space-y-4">
                                <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Avatar Paths</label>
                                <div className="space-y-1.5">
                                    <label className="text-xs font-medium text-zinc-500">Avatar Image Directory</label>
                                    <input
                                        type="text"
                                        value={config.png_dir || ''}
                                        onChange={(e) => updateField('png_dir', e.target.value)}
                                        className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                        placeholder="Path to PNGs..."
                                    />
                                </div>
                            </section>
                            {Object.entries(config.avatar_map || {}).map(([mood, paths]) => (
                                <div key={mood} className="p-4 border border-zinc-100 rounded-xl bg-zinc-50/50">
                                    <h4 className="font-semibold text-sm capitalize mb-3 text-zinc-900">{mood}</h4>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-[10px] font-bold text-zinc-400 uppercase">Idle Path</label>
                                            <input value={paths.idle} onChange={(e) => updateAvatarMap(mood, 'idle', e.target.value)} className="w-full border border-zinc-200 rounded-md py-1.5 px-3 text-xs focus:ring-1 focus:ring-zinc-900 outline-none bg-white" />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-[10px] font-bold text-zinc-400 uppercase">Talking Path</label>
                                            <input value={paths.talking} onChange={(e) => updateAvatarMap(mood, 'talking', e.target.value)} className="w-full border border-zinc-200 rounded-md py-1.5 px-3 text-xs focus:ring-1 focus:ring-zinc-900 outline-none bg-white" />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {activeCategory === 'General' && (
                        <div className="space-y-8">
                            <section className="space-y-4">
                                <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Global Settings</label>
                                <div className="grid gap-4">
                                    <div className="space-y-1.5">
                                        <label className="text-xs font-medium text-zinc-500">Global Language</label>
                                        <select
                                            value={config.language || 'en'}
                                            onChange={(e) => updateField('language', e.target.value)}
                                            className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                        >
                                            <option value="en">English (en)</option>
                                            <option value="it">Italian (it)</option>
                                            <option value="jp">Japanese (jp)</option>
                                            <option value="es">Spanish (es)</option>
                                            <option value="fr">French (fr)</option>
                                            <option value="de">German (de)</option>
                                        </select>
                                        <p className="text-[10px] text-zinc-400">Sets the default language for STT and unified behaviors.</p>
                                    </div>

                                    <div className="space-y-1.5">
                                        <label className="text-xs font-medium text-zinc-500">System Prompt File</label>
                                        <input
                                            type="text"
                                            value={config.system_prompt_path || ''}
                                            onChange={(e) => updateField('system_prompt_path', e.target.value)}
                                            className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                            placeholder="gemini-1-eng.txt"
                                        />
                                        <p className="text-[10px] text-zinc-400">The file loaded from the root directory as Bea's identity.</p>
                                    </div>
                                </div>
                            </section>
                        </div>
                    )}

                    {activeCategory === 'Minecraft' && (
                        <div className="space-y-8">
                            <section>
                                <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Connection Settings</label>
                                <div className="grid gap-4 mt-4">
                                    <div className="space-y-1.5">
                                        <label className="text-xs font-medium text-zinc-500">Server URL</label>
                                        <input
                                            value={config.skills?.minecraft?.server_url || 'ws://localhost:8080'}
                                            onChange={(e) => {
                                                setConfig(prev => ({
                                                    ...prev,
                                                    skills: {
                                                        ...prev.skills,
                                                        minecraft: {
                                                            ...prev.skills.minecraft,
                                                            server_url: e.target.value
                                                        }
                                                    }
                                                }))
                                            }}
                                            className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none transition-all"
                                            placeholder="ws://localhost:8080"
                                        />
                                        <p className="text-[10px] text-zinc-400">WebSocket URL of the Minecraft Mod.</p>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Max History Events</label>
                                            <input
                                                type="number"
                                                value={config.skills?.minecraft?.max_history_events ?? 20}
                                                onChange={(e) => {
                                                    setConfig(prev => ({
                                                        ...prev,
                                                        skills: {
                                                            ...prev.skills,
                                                            minecraft: {
                                                                ...prev.skills.minecraft,
                                                                max_history_events: parseInt(e.target.value)
                                                            }
                                                        }
                                                    }))
                                                }}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                            />
                                        </div>

                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Auto Chat Thoughts</label>
                                            <div className="flex items-center h-[38px] px-3 border border-zinc-200 rounded-md">
                                                <input
                                                    type="checkbox"
                                                    checked={config.skills?.minecraft?.auto_chat_thoughts || false}
                                                    onChange={(e) => {
                                                        setConfig(prev => ({
                                                            ...prev,
                                                            skills: {
                                                                ...prev.skills,
                                                                minecraft: {
                                                                    ...prev.skills.minecraft,
                                                                    auto_chat_thoughts: e.target.checked
                                                                }
                                                            }
                                                        }))
                                                    }}
                                                    className="w-4 h-4 text-zinc-900 rounded focus:ring-zinc-900"
                                                />
                                                <span className="ml-2 text-xs">Post to Minecraft Chat</span>
                                            </div>
                                        </div>

                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Auto Speak Thoughts</label>
                                            <div className="flex items-center h-[38px] px-3 border border-zinc-200 rounded-md">
                                                <input
                                                    type="checkbox"
                                                    checked={config.skills?.minecraft?.auto_speak_thoughts || false}
                                                    onChange={(e) => {
                                                        setConfig(prev => ({
                                                            ...prev,
                                                            skills: {
                                                                ...prev.skills,
                                                                minecraft: {
                                                                    ...prev.skills.minecraft,
                                                                    auto_speak_thoughts: e.target.checked
                                                                }
                                                            }
                                                        }))
                                                    }}
                                                    className="w-4 h-4 text-zinc-900 rounded focus:ring-zinc-900"
                                                />
                                                <span className="ml-2 text-xs">Pipe directly to TTS/OBS</span>
                                            </div>
                                        </div>

                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Debug Mode</label>
                                            <div className="flex items-center h-[38px] px-3 border border-zinc-200 rounded-md">
                                                <input
                                                    type="checkbox"
                                                    checked={config.skills?.minecraft?.debug_mode || false}
                                                    onChange={(e) => {
                                                        setConfig(prev => ({
                                                            ...prev,
                                                            skills: {
                                                                ...prev.skills,
                                                                minecraft: {
                                                                    ...prev.skills.minecraft,
                                                                    debug_mode: e.target.checked
                                                                }
                                                            }
                                                        }))
                                                    }}
                                                    className="w-4 h-4 text-zinc-900 rounded focus:ring-zinc-900"
                                                />
                                                <span className="ml-2 text-xs">Enable Verbose Logging</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="pt-4 border-t border-zinc-100 space-y-4">
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Dedicated OpenAI Model</label>
                                            <input
                                                value={config.skills?.minecraft?.mc_openai_model || 'gpt-4o-mini'}
                                                onChange={(e) => {
                                                    setConfig(prev => ({
                                                        ...prev,
                                                        skills: {
                                                            ...prev.skills,
                                                            minecraft: {
                                                                ...prev.skills.minecraft,
                                                                mc_openai_model: e.target.value
                                                            }
                                                        }
                                                    }))
                                                }}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">Dedicated OpenAI Key (Optional)</label>
                                            <input
                                                type="password"
                                                value={config.skills?.minecraft?.mc_openai_key || ''}
                                                onChange={(e) => {
                                                    setConfig(prev => ({
                                                        ...prev,
                                                        skills: {
                                                            ...prev.skills,
                                                            minecraft: {
                                                                ...prev.skills.minecraft,
                                                                mc_openai_key: e.target.value
                                                            }
                                                        }
                                                    }))
                                                }}
                                                className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                                placeholder="sk-..."
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs font-medium text-zinc-500">System Prompt Overrides</label>
                                            <div className="flex items-center justify-between p-3 border border-zinc-200 rounded-lg bg-zinc-50/50">
                                                <div className="text-sm text-zinc-600">
                                                    {config.skills?.minecraft?.system_prompt
                                                        ? `${config.skills?.minecraft?.system_prompt.length} chars configured`
                                                        : "Using default system prompt"}
                                                </div>
                                                <button
                                                    onClick={() => setIsPromptModalOpen(true)}
                                                    className="flex items-center gap-2 px-3 py-1.5 bg-white border border-zinc-200 shadow-sm rounded-md text-xs font-medium text-zinc-700 hover:text-zinc-900 hover:bg-zinc-50 transition-colors"
                                                >
                                                    <Edit size={14} />
                                                    Edit System Prompt
                                                </button>
                                            </div>

                                            <SystemPromptModal
                                                isOpen={isPromptModalOpen}
                                                onClose={() => setIsPromptModalOpen(false)}
                                                value={config.skills?.minecraft?.system_prompt}
                                                onSave={(newVal) => {
                                                    setConfig(prev => ({
                                                        ...prev,
                                                        skills: {
                                                            ...prev.skills,
                                                            minecraft: {
                                                                ...prev.skills.minecraft,
                                                                system_prompt: newVal
                                                            }
                                                        }
                                                    }));
                                                    setIsPromptModalOpen(false);
                                                }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            </section>
                        </div>
                    )}

                    {activeCategory === 'Discord' && (
                        <div className="space-y-8">
                            <section className="flex items-center space-x-3 p-4 border border-zinc-100 rounded-xl bg-zinc-50/50">
                                <input
                                    type="checkbox"
                                    checked={config.skills?.discord?.enabled || false}
                                    onChange={(e) => updateSkillField('discord', 'enabled', e.target.checked)}
                                    className="w-4 h-4 text-zinc-900 rounded focus:ring-zinc-900"
                                />
                                <div>
                                    <label className="text-sm font-medium text-zinc-900">Enable Discord Bot</label>
                                    <p className="text-xs text-zinc-500">Enables the Discord bot for voice and text interaction.</p>
                                </div>
                            </section>

                            <section className="space-y-4">
                                <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Bot API & Authentication</label>
                                <div className="grid gap-4">
                                    <div className="space-y-1.5">
                                        <label className="text-xs font-medium text-zinc-500">Discord Bot Token</label>
                                        <input
                                            type="password"
                                            value={config.skills?.discord?.token || ''}
                                            onChange={(e) => updateSkillField('discord', 'token', e.target.value)}
                                            className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                            placeholder="Bot Token..."
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <label className="text-xs font-medium text-zinc-500">Target Channel ID</label>
                                        <input
                                            type="text"
                                            value={config.skills?.discord?.target_channel || ''}
                                            onChange={(e) => updateSkillField('discord', 'target_channel', e.target.value)}
                                            className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                            placeholder="Channel ID..."
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <label className="text-xs font-medium text-zinc-500">Bot API Port</label>
                                        <input
                                            type="number"
                                            value={config.skills?.discord?.api_port || 3030}
                                            onChange={(e) => updateSkillField('discord', 'api_port', parseInt(e.target.value))}
                                            className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-zinc-900 outline-none"
                                        />
                                        <p className="text-[10px] text-zinc-400">Port for the Discord bot's internal communication API.</p>
                                    </div>
                                </div>
                            </section>

                            <section className="space-y-4">
                                <label className="text-sm font-medium text-zinc-900 block border-b border-zinc-100 pb-2">Conversation Behavior</label>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <label className="text-xs font-medium text-zinc-500">Interrupt Threshold (ms)</label>
                                        <span className="text-xs font-mono bg-zinc-100 px-2 py-0.5 rounded text-zinc-700">
                                            {config.skills?.discord?.interrupt_threshold_ms || 3000}ms
                                        </span>
                                    </div>
                                    <input
                                        type="range"
                                        min="1000"
                                        max="10000"
                                        step="500"
                                        value={config.skills?.discord?.interrupt_threshold_ms || 3000}
                                        onChange={(e) => updateSkillField('discord', 'interrupt_threshold_ms', parseInt(e.target.value))}
                                        className="w-full accent-black"
                                    />
                                    <p className="text-[10px] text-zinc-400">
                                        How long a user must speak before Bea pauses to listen. Short interjections are buffered without interrupting her.
                                    </p>
                                </div>
                            </section>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
