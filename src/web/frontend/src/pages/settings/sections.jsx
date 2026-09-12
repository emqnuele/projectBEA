import React, { useEffect, useState } from 'react';
import { api } from '../../api';
import { Field, SecretInput, Select, Slider, TextInput, CheckRow } from '../../components/ui/fields';
import { Button } from '../../components/ui/controls';
import { CopyField, Group, ProviderChoice, SecretState, TestButton } from './parts';
import { StagePreview } from './StagePreview';
import { PromptEditor } from './PromptEditor';
import { createSchemaSection } from './SchemaSection';
import { PersonalitySection } from './PersonalitySection';

const LANGUAGES = [
    ['en', 'English'], ['it', 'Italian'], ['jp', 'Japanese'],
    ['es', 'Spanish'], ['fr', 'French'], ['de', 'German'],
];

// --- who she is -------------------------------------------------------------

function MindSection({ config, update, updateSkill }) {
    return (
        <>
            <Group title="Language" description="The default for speech recognition and for how she answers.">
                <Field label="She speaks" htmlFor="language">
                    <Select id="language" value={config.language || 'en'} onChange={(e) => update('language', e.target.value)}>
                        {LANGUAGES.map(([code, name]) => (
                            <option key={code} value={code}>{name}</option>
                        ))}
                    </Select>
                </Field>
            </Group>

            <Group
                title="The files behind her"
                description="Her persona is a file on disk, not a text box. These point at which files."
            >
                <Field
                    label="Soul"
                    help="Who she is. Prepended to every context — chat, game, monologue."
                >
                    <TextInput
                        value={config.soul_path || ''}
                        onChange={(e) => update('soul_path', e.target.value)}
                        placeholder="data/prompts/soul.md"
                        className="font-mono"
                    />
                </Field>
                <Field
                    label="Operating manual"
                    help="How she works: the speak tool, moods, how perceptions read."
                >
                    <TextInput
                        value={config.operating_prompt_path || ''}
                        onChange={(e) => update('operating_prompt_path', e.target.value)}
                        placeholder="data/prompts/operating.md"
                        className="font-mono"
                    />
                </Field>
                <Field
                    label="Chat rules"
                    help="Only used when the operating manual is missing."
                >
                    <TextInput
                        value={config.system_prompt_path || ''}
                        onChange={(e) => update('system_prompt_path', e.target.value)}
                        placeholder="data/prompts/chat.md"
                        className="font-mono"
                    />
                </Field>
            </Group>

            <Group
                title="Memory"
                description="Where what she remembers lives, and how close a match has to be to come back."
            >
                <Field label="Database" help="One SQLite file holding people, the diary and her self-lore.">
                    <TextInput
                        value={config.skills?.memory?.db_path || ''}
                        onChange={(e) => updateSkill('memory', 'db_path', e.target.value)}
                        placeholder="data/bea.db"
                        className="font-mono"
                    />
                </Field>
                <Field label="Embedding model" help="Local, and it runs on CPU. Changing it re-embeds everything.">
                    <TextInput
                        value={config.skills?.memory?.embedding_model || ''}
                        onChange={(e) => updateSkill('memory', 'embedding_model', e.target.value)}
                        className="font-mono"
                    />
                </Field>
                <Slider
                    label="Recall threshold"
                    value={config.skills?.memory?.min_similarity ?? 0.3}
                    onChange={(value) => updateSkill('memory', 'min_similarity', value)}
                    min={0} max={1} step={0.01}
                    format={(v) => v.toFixed(2)}
                />
                <p className="text-[11px] leading-snug text-faint">
                    Lower means she reaches for more, and remembers things that only half fit.
                </p>
            </Group>

            <Group title="Dreaming" description="What she does with the day while she is asleep.">
                <Field label="Nightly pass at" help="Hour of the day, 0–23. She sleeps, rereads, then wakes.">
                    <TextInput
                        type="number" min={0} max={23}
                        value={config.skills?.dream?.hour ?? 4}
                        onChange={(e) => updateSkill('dream', 'hour', parseInt(e.target.value, 10) || 0)}
                        className="w-24"
                    />
                </Field>
            </Group>

            <Group title="Idle thoughts" description="What she does when nothing has happened for a while.">
                <Field label="Speaks up after" help="Seconds of quiet before she says something unprompted.">
                    <TextInput
                        type="number"
                        value={config.skills?.monologue?.interval_seconds ?? 120}
                        onChange={(e) => updateSkill('monologue', 'interval_seconds', parseInt(e.target.value, 10) || 0)}
                        className="w-32"
                    />
                </Field>
            </Group>
        </>
    );
}

// --- what thinks for her ----------------------------------------------------

function EngineSection({ config, update, secrets }) {
    const provider = config.llm_provider;
    const keyField = { openrouter: 'openrouter_key', openai: 'openai_key', groq: 'groq_key' }[provider];
    const modelField = { openrouter: 'openrouter_model', openai: 'openai_model', groq: 'groq_model' }[provider];

    return (
        <>
            <Group title="Provider" description="Where her thinking is done.">
                <ProviderChoice
                    value={provider}
                    onChange={(id) => update('llm_provider', id)}
                    columns={3}
                    options={[
                        { id: 'openrouter', label: 'OpenRouter', blurb: 'One endpoint, almost any model.' },
                        { id: 'openai', label: 'OpenAI', blurb: 'GPT models, called directly.' },
                        { id: 'groq', label: 'Groq', blurb: 'Fastest inference, fewer models.' },
                    ]}
                />
            </Group>

            <Group title="Credentials">
                <Field
                    label="API key"
                    action={<SecretState configured={secrets[keyField]} envHint="saved to .env" />}
                    help="Saved to .env, which is the only file keys are kept in — config.json never carries one. Empty the box to forget the key."
                >
                    <SecretInput
                        value={config[keyField] || ''}
                        onChange={(e) => update(keyField, e.target.value)}
                        placeholder={provider === 'openrouter' ? 'sk-or-…' : 'sk-…'}
                    />
                </Field>

                <Field label="Model" help="The exact identifier the provider expects.">
                    <TextInput
                        value={config[modelField] || ''}
                        onChange={(e) => update(modelField, e.target.value)}
                        placeholder={provider === 'openrouter' ? 'deepseek/deepseek-v4-flash' : 'gpt-4o-mini'}
                        className="font-mono"
                    />
                </Field>

                <TestButton label="Ask the model something" run={api.testLlm} />
            </Group>
        </>
    );
}

// --- how she sounds ---------------------------------------------------------

function VoiceSection({ config, update, secrets, devices }) {
    const provider = config.tts_provider;

    return (
        <>
            <Group title="Engine" description="Changing this needs the engine restarted.">
                <ProviderChoice
                    value={provider}
                    onChange={(id) => update('tts_provider', id)}
                    columns={3}
                    options={[
                        { id: 'edge', label: 'Edge', blurb: 'Free and quick, needs the network.' },
                        { id: 'kokoro', label: 'Kokoro', blurb: 'Local ONNX. Best balance.' },
                        { id: 'orpheus', label: 'Orpheus', blurb: 'Hosted, most expressive.' },
                    ]}
                />
            </Group>

            {provider === 'edge' && (
                <Group title="Edge voice">
                    <Field label="Voice" help="For example en-US-AvaNeural.">
                        <TextInput value={config.tts_voice || ''} onChange={(e) => update('tts_voice', e.target.value)} className="font-mono" />
                    </Field>
                    <div className="grid gap-3 sm:grid-cols-3">
                        <Field label="Pitch"><TextInput value={config.tts_pitch || ''} onChange={(e) => update('tts_pitch', e.target.value)} placeholder="+0Hz" /></Field>
                        <Field label="Rate"><TextInput value={config.tts_rate || ''} onChange={(e) => update('tts_rate', e.target.value)} placeholder="+0%" /></Field>
                        <Field label="Volume"><TextInput value={config.tts_volume || ''} onChange={(e) => update('tts_volume', e.target.value)} placeholder="+0%" /></Field>
                    </div>
                </Group>
            )}

            {provider === 'kokoro' && (
                <Group title="Kokoro voice">
                    <Field label="Voice" help="af_bella, af_sarah, af_sky, am_adam, bm_george…">
                        <TextInput value={config.kokoro_voice || ''} onChange={(e) => update('kokoro_voice', e.target.value)} className="font-mono" />
                    </Field>
                    <div className="grid gap-3 sm:grid-cols-2">
                        <Field label="Speed">
                            <TextInput
                                type="number" step="0.1"
                                value={config.kokoro_speed ?? 1}
                                onChange={(e) => update('kokoro_speed', parseFloat(e.target.value))}
                            />
                        </Field>
                        <Field label="Language">
                            <TextInput value={config.kokoro_lang || ''} onChange={(e) => update('kokoro_lang', e.target.value)} placeholder="en-us" />
                        </Field>
                    </div>
                </Group>
            )}

            {provider === 'orpheus' && (
                <Group title="Orpheus voice">
                    <Field label="API key" action={<SecretState configured={secrets.orpheus_key} />}>
                        <SecretInput value={config.orpheus_key || ''} onChange={(e) => update('orpheus_key', e.target.value)} />
                    </Field>
                    <Field label="Endpoint" action={<SecretState configured={secrets.orpheus_endpoint} />}>
                        <SecretInput value={config.orpheus_endpoint || ''} onChange={(e) => update('orpheus_endpoint', e.target.value)} placeholder="https://model-…" />
                    </Field>
                    <Field label="Voice">
                        <TextInput value={config.orpheus_voice || ''} onChange={(e) => update('orpheus_voice', e.target.value)} placeholder="tara" />
                    </Field>
                </Group>
            )}

            <Group
                title="Where the audio goes"
                description="Point this at the virtual cable OBS is listening to, not at your speakers."
            >
                <Field label="Output device">
                    {devices.length > 0 ? (
                        <Select
                            value={config.audio_device_id ?? 0}
                            onChange={(e) => update('audio_device_id', parseInt(e.target.value, 10))}
                        >
                            {devices.map((device) => (
                                <option key={device.id} value={device.id}>
                                    {device.id} — {device.name}
                                </option>
                            ))}
                        </Select>
                    ) : (
                        <TextInput
                            type="number"
                            value={config.audio_device_id ?? 0}
                            onChange={(e) => update('audio_device_id', parseInt(e.target.value, 10) || 0)}
                            className="w-32"
                        />
                    )}
                </Field>
                <TestButton label="Render a test line" run={api.testTts} />
            </Group>
        </>
    );
}

// --- how she hears ----------------------------------------------------------

function HearingSection({ config, update }) {
    return (
        <Group title="Speech to text" description="Changing the provider needs the engine restarted.">
            <ProviderChoice
                value={config.stt_provider}
                onChange={(id) => update('stt_provider', id)}
                options={[
                    { id: 'groq', label: 'Groq Whisper', blurb: 'whisper-large-v3-turbo, very fast.' },
                    { id: 'openrouter', label: 'OpenRouter', blurb: 'openai/whisper-large-v3-turbo.' },
                ]}
            />
            <Field label="Model" help="Leave empty to use the provider's default.">
                <TextInput
                    value={config.stt_model || ''}
                    onChange={(e) => update('stt_model', e.target.value)}
                    placeholder={config.stt_provider === 'openrouter' ? 'openai/whisper-large-v3-turbo' : 'whisper-large-v3-turbo'}
                    className="font-mono"
                />
            </Field>
        </Group>
    );
}

// --- the stream -------------------------------------------------------------

/** One row per mood, so a map is edited where the moods actually are. */
function MoodMap({ moods, values, onChange, placeholder, options }) {
    if (!moods.length) return <p className="text-[12px] text-faint">No moods are configured.</p>;
    return (
        <div className="grid gap-2">
            {moods.map((mood) => (
                <div key={mood} className="grid items-center gap-2 sm:grid-cols-[7rem_1fr]">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-dim">{mood}</span>
                    {options ? (
                        <Select value={values[mood] || ''} onChange={(e) => onChange(mood, e.target.value)}>
                            <option value="">— none —</option>
                            {options.map((o) => (
                                <option key={o.id} value={o.id}>{o.label}</option>
                            ))}
                        </Select>
                    ) : (
                        <TextInput
                            value={values[mood] || ''}
                            onChange={(e) => onChange(mood, e.target.value)}
                            placeholder={placeholder}
                            className="font-mono text-[11px]"
                        />
                    )}
                </div>
            ))}
        </div>
    );
}

function VTubeStudioGroups({ stage, moods, updateStage, updateStageMap, model, setModel }) {
    // one call does both jobs: it reports the connection and fills the pickers
    const load = async () => {
        const found = await api.vtsModel();
        setModel(found);
        return {
            ok: found.ok,
            message: found.message,
            detail: found.ok
                ? `${found.expressions.length} expressions, ${found.hotkeys.length} hotkeys`
                : null,
        };
    };

    return (
        <>
            <Group title="VTube Studio" description="Not bundled and not required: if you run it, she can drive it. Your model stays yours.">
                <div className="grid gap-3 sm:grid-cols-[1fr_7rem]">
                    <Field label="Host">
                        <TextInput value={stage.vts_host || ''} onChange={(e) => updateStage('vts_host', e.target.value)} className="font-mono" />
                    </Field>
                    <Field label="Port" help="8001 by default.">
                        <TextInput type="number" value={stage.vts_port ?? 8001} onChange={(e) => updateStage('vts_port', parseInt(e.target.value, 10) || 0)} />
                    </Field>
                </div>
                <p className="text-[11px] leading-snug text-faint">
                    The first time she connects, VTube Studio asks you to allow the plugin. Say yes in its window;
                    the token is stored under <span className="font-mono">data/</span> and never leaves this machine.
                </p>
                <TestButton label="Test the connection" run={load} />
            </Group>

            <Group title="A face per mood" description="Expressions come from your model, so pick from what it actually has.">
                <MoodMap
                    moods={moods}
                    values={stage.vts_expressions || {}}
                    onChange={(mood, value) => updateStageMap('vts_expressions', mood, value)}
                    placeholder="angry.exp3.json"
                    options={model?.expressions?.map((name) => ({ id: name, label: name }))}
                />
            </Group>

            <Group title="A behaviour per mood" description="Hotkeys as your model defines them.">
                <MoodMap
                    moods={moods}
                    values={stage.vts_clips || {}}
                    onChange={(mood, value) => updateStageMap('vts_clips', mood, value)}
                    placeholder="hotkey id"
                    options={model?.hotkeys?.map((h) => ({ id: h.id, label: h.name || h.id }))}
                />
            </Group>
        </>
    );
}

const AVATAR_BACKENDS = [
    { id: 'png', label: 'Images', blurb: 'One picture per mood, swapped in OBS.' },
    { id: 'model', label: '3D model', blurb: 'A VRM you bring, rendered in a browser source.' },
    { id: 'vtube_studio', label: 'VTube Studio', blurb: 'Your own Live2D model, driven over its API.' },
];

const CAPTION_BACKENDS = [
    { id: 'obs', label: 'OBS text', blurb: 'Typed into a text source.' },
    { id: 'stage', label: 'Browser source', blurb: 'Typed in the page, one message instead of one per letter.' },
    { id: 'off', label: 'Off', blurb: 'She speaks, nothing is written.' },
];

function StreamSection({ config, update, setConfig }) {
    const stage = config.stage || {};
    const avatarBackend = stage.avatar_backend || 'png';
    const captionBackend = stage.caption_backend || 'obs';

    const updateStage = (key, value) => setConfig((prev) => ({
        ...prev,
        stage: { ...(prev.stage || {}), [key]: value },
    }));
    const updateStageMap = (key, mood, value) => setConfig((prev) => ({
        ...prev,
        stage: { ...(prev.stage || {}), [key]: { ...((prev.stage || {})[key] || {}), [mood]: value } },
    }));
    const updateAvatar = (mood, state, value) => setConfig((prev) => ({
        ...prev,
        avatar_map: { ...prev.avatar_map, [mood]: { ...prev.avatar_map[mood], [state]: value } },
    }));

    const needsObs = avatarBackend === 'png' || captionBackend === 'obs';
    const moods = Object.keys(config.avatar_map || {});
    const stageUrl = `${window.location.origin}/stage`;

    // what is actually installed in the clips folder, so the picker offers real
    // names instead of a text box where a typo is silent until you are live
    const [clips, setClips] = useState([]);
    // what VTube Studio answered, held here so the preview and the pickers are
    // looking at the same connection instead of each asking on their own
    const [vtsModel, setVtsModel] = useState(null);
    useEffect(() => {
        if (avatarBackend !== 'model') return;
        api.stageClips().then(setClips).catch(() => setClips([]));
    }, [avatarBackend, stage.clips_dir]);

    return (
        <>
            <Group title="How she appears" description="Two independent choices: the body, and the words on screen.">
                <Field label="Avatar" help="What the audience actually sees of her.">
                    <ProviderChoice
                        value={avatarBackend}
                        onChange={(id) => updateStage('avatar_backend', id)}
                        options={AVATAR_BACKENDS}
                        columns={3}
                    />
                </Field>
                <Field label="Speech bubble" help="How her words are shown while she talks.">
                    <ProviderChoice
                        value={captionBackend}
                        onChange={(id) => updateStage('caption_backend', id)}
                        options={CAPTION_BACKENDS}
                        columns={3}
                    />
                </Field>
            </Group>

            <StagePreview config={config} vtsStatus={vtsModel} />

            {(avatarBackend === 'model' || captionBackend === 'stage') && (
                <Group title="The browser source" description="Add this URL to OBS as a Browser Source. Tick 'Shutdown source when not visible' off, so she keeps her pose.">
                    <CopyField value={stageUrl} />
                </Group>
            )}

            {needsObs && (
                <Group title="OBS" description="She swaps the avatar and types into a text source over WebSocket.">
                    <div className="grid gap-3 sm:grid-cols-[1fr_7rem]">
                        <Field label="Host"><TextInput value={config.obs_host || ''} onChange={(e) => update('obs_host', e.target.value)} className="font-mono" /></Field>
                        <Field label="Port">
                            <TextInput
                                type="number"
                                value={config.obs_port ?? 4455}
                                onChange={(e) => update('obs_port', parseInt(e.target.value, 10) || 0)}
                            />
                        </Field>
                    </div>
                    <Field label="Password">
                        <SecretInput value={config.obs_password || ''} onChange={(e) => update('obs_password', e.target.value)} />
                    </Field>
                    <TestButton label="Connect to OBS" run={api.testObs} />
                </Group>
            )}

            {(avatarBackend === 'png' || captionBackend === 'obs') && (
                <Group title="Sources" description="The names exactly as they appear in your OBS scene.">
                    {avatarBackend === 'png' && (
                        <>
                            <ProviderChoice
                                value={config.obs_source_type}
                                onChange={(id) => update('obs_source_type', id)}
                                options={[
                                    { id: 'image', label: 'Image source', blurb: 'Static PNG avatars.' },
                                    { id: 'media', label: 'Media source', blurb: 'Video or animated files.' },
                                ]}
                            />
                            <Field label="Avatar source">
                                <TextInput value={config.obs_avatar_source || ''} onChange={(e) => update('obs_avatar_source', e.target.value)} className="font-mono" />
                            </Field>
                        </>
                    )}
                    {captionBackend === 'obs' && (
                        <Field label="Text source">
                            <TextInput value={config.obs_text_source || ''} onChange={(e) => update('obs_text_source', e.target.value)} className="font-mono" />
                        </Field>
                    )}
                </Group>
            )}

            {captionBackend !== 'off' && (
                <Group title="The text bubble" description="How her words appear on screen while she talks.">
                    <div className="grid gap-3 sm:grid-cols-2">
                        <Field label="Line width">
                            <TextInput type="number" value={config.text_line_width ?? 0} onChange={(e) => update('text_line_width', parseInt(e.target.value, 10) || 0)} />
                        </Field>
                        <Field label="Font size">
                            <TextInput type="number" value={config.text_font_size ?? 0} onChange={(e) => update('text_font_size', parseInt(e.target.value, 10) || 0)} />
                        </Field>
                        <Field label="Typing delay" help="Seconds between characters.">
                            <TextInput type="number" step="0.01" value={config.typing_delay ?? 0} onChange={(e) => update('typing_delay', parseFloat(e.target.value))} />
                        </Field>
                        <Field label="Minimum time on screen" help="Seconds a short line stays up.">
                            <TextInput type="number" step="0.1" value={config.text_min_duration ?? 2} onChange={(e) => update('text_min_duration', parseFloat(e.target.value))} />
                        </Field>
                    </div>
                </Group>
            )}

            {avatarBackend === 'png' && (
                <Group title="Avatar" description="One image per mood, one for idle and one for talking.">
                    <Field label="Image folder">
                        <TextInput value={config.png_dir || ''} onChange={(e) => update('png_dir', e.target.value)} className="font-mono" />
                    </Field>
                    {Object.entries(config.avatar_map || {}).map(([mood, paths]) => (
                        <div key={mood} className="rounded-b2 border border-line bg-fill p-3">
                            <p className="mb-2.5 font-mono text-[10px] uppercase tracking-wider text-dim">{mood}</p>
                            <div className="grid gap-2.5 sm:grid-cols-2">
                                <Field label="Idle">
                                    <TextInput value={paths.idle || ''} onChange={(e) => updateAvatar(mood, 'idle', e.target.value)} className="font-mono text-[11px]" />
                                </Field>
                                <Field label="Talking">
                                    <TextInput value={paths.talking || ''} onChange={(e) => updateAvatar(mood, 'talking', e.target.value)} className="font-mono text-[11px]" />
                                </Field>
                            </div>
                        </div>
                    ))}
                </Group>
            )}

            {avatarBackend === 'model' && (
                <>
                    <Group title="The model" description="A .vrm file on this machine. Nothing is bundled: the model is yours.">
                        <Field label="Model file" help="Run `make model` to download the free sample, or point this at your own.">
                            <TextInput value={stage.model_path || ''} onChange={(e) => updateStage('model_path', e.target.value)} placeholder="data/models/bea.vrm" className="font-mono" />
                        </Field>
                        <Field label="Framing" help="Computed from the head bone, so any model is framed the same way.">
                            <ProviderChoice
                                value={stage.shot || 'bust'}
                                onChange={(id) => updateStage('shot', id)}
                                options={[
                                    { id: 'bust', label: 'Bust', blurb: 'Head and shoulders.' },
                                    { id: 'half', label: 'Half', blurb: 'From the hips up.' },
                                    { id: 'full', label: 'Full', blurb: 'All of her.' },
                                ]}
                                columns={3}
                            />
                        </Field>
                        <div className="grid gap-3 sm:grid-cols-2">
                            <Field label="Behaviours folder" help="The .vrma clips she can play.">
                                <TextInput value={stage.clips_dir || ''} onChange={(e) => updateStage('clips_dir', e.target.value)} className="font-mono" />
                            </Field>
                            <Field label="Lip sync rate" help="Mouth updates per second.">
                                <TextInput type="number" value={stage.lipsync_fps ?? 30} onChange={(e) => updateStage('lipsync_fps', parseInt(e.target.value, 10) || 30)} />
                            </Field>
                        </div>
                    </Group>

                    <Group title="A behaviour per mood" description="Optional. Leave one empty and she just changes expression.">
                        <MoodMap
                            moods={moods}
                            values={stage.mood_clips || {}}
                            onChange={(mood, value) => updateStageMap('mood_clips', mood, value)}
                            placeholder="wave"
                            options={(clips || []).map((name) => ({ id: name, label: name }))}
                        />
                    </Group>
                </>
            )}

            {avatarBackend === 'vtube_studio' && (
                <VTubeStudioGroups
                    stage={stage}
                    moods={moods}
                    updateStage={updateStage}
                    updateStageMap={updateStageMap}
                    model={vtsModel}
                    setModel={setVtsModel}
                />
            )}
        </>
    );
}

// --- where she is -----------------------------------------------------------

// --- her body ---------------------------------------------------------------

function WorldSection({ config, updateSkill }) {
    const [promptOpen, setPromptOpen] = useState(false);
    const minecraft = config.skills?.minecraft || {};

    return (
        <>
            <Group title="The server" description="She connects to the mod over a WebSocket.">
                <CheckRow
                    checked={minecraft.enabled}
                    onChange={(value) => updateSkill('minecraft', 'enabled', value)}
                    title="Give her a body on the server"
                />
                <Field label="Mod address">
                    <TextInput
                        value={minecraft.server_url || ''}
                        onChange={(e) => updateSkill('minecraft', 'server_url', e.target.value)}
                        placeholder="ws://127.0.0.1:8080"
                        className="font-mono"
                    />
                </Field>
            </Group>

            <Group title="What she does with a thought in-game">
                <CheckRow
                    checked={minecraft.auto_chat_thoughts}
                    onChange={(value) => updateSkill('minecraft', 'auto_chat_thoughts', value)}
                    title="Post it to the game chat"
                    help="Other players on the server see it."
                />
                <CheckRow
                    checked={minecraft.auto_speak_thoughts}
                    onChange={(value) => updateSkill('minecraft', 'auto_speak_thoughts', value)}
                    title="Say it out loud"
                    help="Goes straight to the voice engine and the stream overlay."
                />
            </Group>

            <Group title="Instructions" description="How she behaves in the world. Uses the engine's main model.">
                <div className="flex items-center justify-between gap-3 rounded-b2 border border-line bg-fill p-3">
                    <span className="text-[12px] text-dim">
                        {minecraft.system_prompt
                            ? `Custom instructions — ${minecraft.system_prompt.length} characters`
                            : 'Using the default instructions'}
                    </span>
                    <Button size="sm" variant="outline" onClick={() => setPromptOpen(true)}>Edit</Button>
                </div>
                <PromptEditor
                    open={promptOpen}
                    value={minecraft.system_prompt || ''}
                    onClose={() => setPromptOpen(false)}
                    onSave={(text) => { updateSkill('minecraft', 'system_prompt', text); setPromptOpen(false); }}
                />
            </Group>
        </>
    );
}

// Everything the engine declares renders itself; the rest is hand-built because
// it does more than set a value (file pickers, provider trade-offs, live tests).
const SCHEMA_DRIVEN = [
    'models', 'attention', 'rhythm', 'discord', 'telegram', 'twitch', 'donations',
];

export const SECTIONS = {
    personality: PersonalitySection,
    mind: MindSection,
    engine: EngineSection,
    voice: VoiceSection,
    hearing: HearingSection,
    stream: StreamSection,
    world: WorldSection,
    ...Object.fromEntries(SCHEMA_DRIVEN.map((key) => [key, createSchemaSection(key)])),
};
