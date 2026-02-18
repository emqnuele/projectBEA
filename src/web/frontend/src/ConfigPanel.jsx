import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from './components/ui/card'
import { Input } from './components/ui/input'
import { Label } from './components/ui/label'
import { Button } from './components/ui/button'
import { Switch } from './components/ui/switch'
import { Separator } from './components/ui/separator'

const API_BASE = 'http://localhost:8000'

export default function ConfigPanel() {
    const [config, setConfig] = useState(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [activeCategory, setActiveCategory] = useState("LLM")

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
        setSaving(true)
        try {
            const res = await fetch(`${API_BASE}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            })
            if (res.ok) {
                alert('Configuration Saved!')
            } else {
                alert('Error saving configuration')
            }
        } catch (e) {
            alert(e.message)
        } finally {
            setSaving(false)
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

    if (loading || !config) return <div className="p-10 text-center">Loading Settings...</div>

    const CategoryButton = ({ name }) => (
        <button
            onClick={() => setActiveCategory(name)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors text-left
            ${activeCategory === name ? 'bg-primary text-primary-foreground' : 'text-gray-600 hover:bg-gray-100'}
        `}
        >
            {name}
        </button>
    )

    return (
        <div className="flex gap-6 h-[600px]">
            {/* sidebar nav */}
            <div className="w-48 flex flex-col gap-1 pr-4 border-r border-gray-100">
                <CategoryButton name="LLM" />
                <CategoryButton name="TTS" />
                <CategoryButton name="OBS" />
                <CategoryButton name="Typing" />
                <CategoryButton name="Avatar" />
                <CategoryButton name="Memory" />
                <CategoryButton name="Discord" />
            </div>

            {/* content area */}
            <div className="flex-1 overflow-y-auto pr-2">
                <Card>
                    <CardHeader>
                        <CardTitle>{activeCategory} Settings</CardTitle>
                        <CardDescription>Configure parameters for {activeCategory}.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6">

                        {activeCategory === 'LLM' && (
                            <>
                                <div className="space-y-1">
                                    <Label>LLM Provider</Label>
                                    <div className="flex gap-4">
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="radio"
                                                name="llm_provider"
                                                checked={config.llm_provider === 'gemini'}
                                                onChange={() => updateField('llm_provider', 'gemini')}
                                            /> Gemini
                                        </label>
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="radio"
                                                name="llm_provider"
                                                checked={config.llm_provider === 'glm'}
                                                onChange={() => updateField('llm_provider', 'glm')}
                                            /> GLM
                                        </label>
                                    </div>
                                </div>

                                <Separator />

                                <div className="space-y-1">
                                    <Label>Gemini API Key</Label>
                                    <Input
                                        type="password"
                                        value={config.gemini_key || ''}
                                        onChange={(e) => updateField('gemini_key', e.target.value)}
                                        placeholder="AIza..."
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label>Gemini Model</Label>
                                    <Input
                                        value={config.gemini_model || ''}
                                        onChange={(e) => updateField('gemini_model', e.target.value)}
                                    />
                                </div>

                                <Separator />

                                <div className="space-y-1">
                                    <Label>GLM API Key</Label>
                                    <Input
                                        type="password"
                                        value={config.glm_key || ''}
                                        onChange={(e) => updateField('glm_key', e.target.value)}
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label>GLM Model</Label>
                                    <Input
                                        value={config.glm_model || ''}
                                        onChange={(e) => updateField('glm_model', e.target.value)}
                                    />
                                </div>

                                <Separator />
                                <div className="space-y-1">
                                    <Label>System Prompt Path</Label>
                                    <Input
                                        value={config.system_prompt_path || ''}
                                        onChange={(e) => updateField('system_prompt_path', e.target.value)}
                                    />
                                </div>
                            </>
                        )}

                        {activeCategory === 'TTS' && (
                            <>
                                <div className="space-y-1">
                                    <Label>TTS Provider</Label>
                                    <div className="flex gap-4">
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="radio"
                                                name="tts_provider"
                                                checked={config.tts_provider === 'edge'}
                                                onChange={() => updateField('tts_provider', 'edge')}
                                            /> EdgeTTS (Free, Fast)
                                        </label>
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="radio"
                                                name="tts_provider"
                                                checked={config.tts_provider === 'edge'}
                                                onChange={() => updateField('tts_provider', 'edge')}
                                            /> EdgeTTS (Free, Fast)
                                        </label>
                                        {/* Coqui TTS Removed */}
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="radio"
                                                name="tts_provider"
                                                checked={config.tts_provider === 'kokoro'}
                                                onChange={() => updateField('tts_provider', 'kokoro')}
                                            /> Kokoro ONNX (Local, Fast)
                                        </label>
                                    </div>
                                </div>

                                <Separator />

                                {config.tts_provider === 'edge' && (
                                    <div className="space-y-1">
                                        <Label>Edge Voice</Label>
                                        <Input
                                            value={config.tts_voice || ''}
                                            onChange={(e) => updateField('tts_voice', e.target.value)}
                                        />
                                    </div>
                                )}

                                {config.tts_provider === 'coqui' && (
                                    <div className="p-4 bg-yellow-50 text-yellow-800 rounded text-sm">
                                        Coqui TTS has been removed to optimize dependencies. Please select another provider.
                                    </div>
                                )}

                                {config.tts_provider === 'kokoro' && (
                                    <>
                                        <div className="space-y-1">
                                            <Label>Voice</Label>
                                            <Input
                                                value={config.kokoro_voice || ''}
                                                onChange={(e) => updateField('kokoro_voice', e.target.value)}
                                            />
                                            <p className="text-xs text-muted-foreground">e.g. af_bella, af_sky, am_adam, bm_lewis...</p>
                                        </div>
                                        <div className="space-y-1">
                                            <Label>Speed</Label>
                                            <Input
                                                type="number"
                                                step="0.1"
                                                value={config.kokoro_speed || 1.0}
                                                onChange={(e) => updateField('kokoro_speed', parseFloat(e.target.value))}
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label>Language</Label>
                                            <Input
                                                value={config.kokoro_lang || 'en-us'}
                                                onChange={(e) => updateField('kokoro_lang', e.target.value)}
                                            />
                                        </div>
                                    </>
                                )}

                                <Separator />
                                <div className="space-y-1">
                                    <Label>Audio Output Device ID</Label>
                                    <Input
                                        type="number"
                                        value={config.audio_device_id || 0}
                                        onChange={(e) => updateField('audio_device_id', parseInt(e.target.value))}
                                    />
                                    <p className="text-xs text-muted-foreground">ID 29 for VB-Cable, 24 for default often.</p>
                                </div>
                            </>
                        )}

                        {activeCategory === 'OBS' && (
                            <>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-1">
                                        <Label>Host</Label>
                                        <Input
                                            value={config.obs_host || ''}
                                            onChange={(e) => updateField('obs_host', e.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <Label>Port</Label>
                                        <Input
                                            type="number"
                                            value={config.obs_port || 4455}
                                            onChange={(e) => updateField('obs_port', parseInt(e.target.value))}
                                        />
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <Label>Password</Label>
                                    <Input
                                        type="password"
                                        value={config.obs_password || ''}
                                        onChange={(e) => updateField('obs_password', e.target.value)}
                                    />
                                </div>
                                <Separator />
                                <div className="space-y-1">
                                    <Label>Image Source Name</Label>
                                    <Input
                                        value={config.obs_image_source || ''}
                                        onChange={(e) => updateField('obs_image_source', e.target.value)}
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label>Text Source Name</Label>
                                    <Input
                                        value={config.obs_text_source || ''}
                                        onChange={(e) => updateField('obs_text_source', e.target.value)}
                                    />
                                </div>
                            </>
                        )}

                        {activeCategory === 'Typing' && (
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-1">
                                    <Label>Line Width (chars)</Label>
                                    <Input
                                        type="number"
                                        value={config.text_line_width || 50}
                                        onChange={(e) => updateField('text_line_width', parseInt(e.target.value))}
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label>Base Font Size</Label>
                                    <Input
                                        type="number"
                                        value={config.text_font_size || 75}
                                        onChange={(e) => updateField('text_font_size', parseInt(e.target.value))}
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label>Typing Delay (sec)</Label>
                                    <Input
                                        type="number"
                                        step="0.01"
                                        value={config.typing_delay || 0.03}
                                        onChange={(e) => updateField('typing_delay', parseFloat(e.target.value))}
                                    />
                                </div>
                            </div>
                        )}

                        {activeCategory === 'Avatar' && (
                            <div className="space-y-4">
                                <p className="text-sm text-muted-foreground">Paths to PNG files for each mood.</p>
                                {Object.entries(config.avatar_map || {}).map(([mood, paths]) => (
                                    <div key={mood} className="border p-4 rounded-lg bg-gray-50/50">
                                        <h4 className="font-semibold text-sm mb-2 capitalize">{mood}</h4>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="space-y-1">
                                                <Label className="text-xs">Idle Path</Label>
                                                <Input
                                                    className="text-xs h-8"
                                                    value={paths.idle}
                                                    onChange={(e) => updateAvatarMap(mood, 'idle', e.target.value)}
                                                />
                                            </div>
                                            <div className="space-y-1">
                                                <Label className="text-xs">Talking Path</Label>
                                                <Input
                                                    className="text-xs h-8"
                                                    value={paths.talking}
                                                    onChange={(e) => updateAvatarMap(mood, 'talking', e.target.value)}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {activeCategory === 'Memory' && (
                            <>
                                <div className="flex items-center space-x-2">
                                    <Switch
                                        checked={config.memory_enabled || false}
                                        onCheckedChange={(checked) => updateField('memory_enabled', checked)}
                                    />
                                    <Label>Enable Long-Term Memory (RAG)</Label>
                                </div>
                                <p className="text-sm text-muted-foreground">
                                    Enables the bot to remember past conversations by generating diary entries and storing them in a local Vector DB.
                                </p>

                                <Separator />

                                <div className="space-y-1">
                                    <Label>ChromaDB Path</Label>
                                    <Input
                                        value={config.memory_chroma_path || 'data/memory_db'}
                                        onChange={(e) => updateField('memory_chroma_path', e.target.value)}
                                    />
                                </div>

                                <div className="space-y-1">
                                    <Label>Diary Generation Model</Label>
                                    <Input
                                        value={config.memory_openai_model || 'gpt-4o-mini'}
                                        onChange={(e) => updateField('memory_openai_model', e.target.value)}
                                    />
                                    <p className="text-xs text-muted-foreground">Model used to summarize conversations into diary entries.</p>
                                </div>

                                <div className="space-y-1">
                                    <Label>Embedding Model</Label>
                                    <Input
                                        value={config.memory_embedding_model || 'text-embedding-3-small'}
                                        onChange={(e) => updateField('memory_embedding_model', e.target.value)}
                                    />
                                </div>
                            </>
                        )}

                        {activeCategory === 'Discord' && (
                            <>
                                <div className="flex items-center space-x-2">
                                    <Switch
                                        checked={config.skills?.discord?.enabled || false}
                                        onCheckedChange={(checked) => updateSkillField('discord', 'enabled', checked)}
                                    />
                                    <Label>Enable Discord Bot</Label>
                                </div>
                                <p className="text-sm text-muted-foreground">
                                    Enables the Discord bot for voice and text interaction.
                                </p>

                                <Separator />

                                <div className="space-y-1">
                                    <Label>Discord Token</Label>
                                    <Input
                                        type="password"
                                        value={config.skills?.discord?.token || ''}
                                        onChange={(e) => updateSkillField('discord', 'token', e.target.value)}
                                        placeholder="Bot token..."
                                    />
                                </div>

                                <div className="space-y-1">
                                    <Label>Target Channel ID</Label>
                                    <Input
                                        value={config.skills?.discord?.target_channel || ''}
                                        onChange={(e) => updateSkillField('discord', 'target_channel', e.target.value)}
                                        placeholder="Channel ID..."
                                    />
                                </div>

                                <div className="space-y-1">
                                    <Label>Bot API Port</Label>
                                    <Input
                                        type="number"
                                        value={config.skills?.discord?.api_port || 3030}
                                        onChange={(e) => updateSkillField('discord', 'api_port', parseInt(e.target.value))}
                                    />
                                    <p className="text-xs text-muted-foreground">Port for the Discord bot's internal Express API.</p>
                                </div>

                                <Separator />

                                <div className="space-y-2">
                                    <Label>Interrupt Threshold</Label>
                                    <div className="flex items-center gap-4">
                                        <input
                                            type="range"
                                            min="1000"
                                            max="8000"
                                            step="500"
                                            value={config.skills?.discord?.interrupt_threshold_ms || 3000}
                                            onChange={(e) => updateSkillField('discord', 'interrupt_threshold_ms', parseInt(e.target.value))}
                                            className="flex-1"
                                        />
                                        <span className="text-sm font-mono w-16 text-right">
                                            {((config.skills?.discord?.interrupt_threshold_ms || 3000) / 1000).toFixed(1)}s
                                        </span>
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                        How long someone must speak before Bea stops talking. Short sounds below this threshold are buffered silently.
                                    </p>
                                </div>
                            </>
                        )}




                    </CardContent>
                    <CardFooter className="flex justify-between border-t border-gray-100 pt-6">
                        <p className="text-xs text-muted-foreground">Changes are applied immediately upon save.</p>
                        <Button onClick={handleSave} disabled={saving} className="bg-black text-white hover:bg-gray-800">
                            {saving ? 'Saving...' : 'Save Configuration'}
                        </Button>
                    </CardFooter>
                </Card>
            </div>
        </div >
    )
}
