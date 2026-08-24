import React, { useState } from 'react';
import { api } from '../../api';
import { Field, SecretInput, Select, Slider, TextInput, CheckRow } from '../../components/ui/fields';
import { Button } from '../../components/ui/controls';
import { Group, ProviderChoice, SecretState, TestButton } from './parts';
import { PromptEditor } from './PromptEditor';

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
                    action={<SecretState configured={secrets[keyField]} envHint="env wins" />}
                    help="The environment variable always wins. Anything typed here is the fallback written to config.json."
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

function StreamSection({ config, update, setConfig }) {
    const updateAvatar = (mood, state, value) => setConfig((prev) => ({
        ...prev,
        avatar_map: { ...prev.avatar_map, [mood]: { ...prev.avatar_map[mood], [state]: value } },
    }));

    return (
        <>
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

            <Group title="Sources" description="The names exactly as they appear in your OBS scene.">
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
                <Field label="Text source">
                    <TextInput value={config.obs_text_source || ''} onChange={(e) => update('obs_text_source', e.target.value)} className="font-mono" />
                </Field>
            </Group>

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

            <Group title="Avatar" description="One image per mood, one for idle and one for talking.">
                <Field label="Image folder">
                    <TextInput value={config.png_dir || ''} onChange={(e) => update('png_dir', e.target.value)} className="font-mono" />
                </Field>
                {Object.entries(config.avatar_map || {}).map(([mood, paths]) => (
                    <div key={mood} className="rounded-b2 border border-line bg-white/[0.02] p-3">
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
        </>
    );
}

// --- where she is -----------------------------------------------------------

function ChannelsSection({ config, updateSkill, secrets }) {
    const skills = config.skills || {};

    return (
        <>
            <Group title="Discord" description="Text channels and voice calls, each its own conversation.">
                <CheckRow
                    checked={skills.discord?.enabled}
                    onChange={(value) => updateSkill('discord', 'enabled', value)}
                    title="Let her onto Discord"
                    help="The bot process starts with the engine."
                />
                <Field label="Bot token" action={<SecretState configured={secrets['discord.token']} />}>
                    <SecretInput
                        value={skills.discord?.token || ''}
                        onChange={(e) => updateSkill('discord', 'token', e.target.value)}
                        placeholder="Paste a token to replace the stored one"
                    />
                </Field>
                <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Bot API port" help="How the bot and the brain talk to each other.">
                        <TextInput
                            type="number"
                            value={skills.discord?.api_port ?? 3030}
                            onChange={(e) => updateSkill('discord', 'api_port', parseInt(e.target.value, 10) || 0)}
                        />
                    </Field>
                    <Field label="Admin id" help="Whose messages count as her owner's.">
                        <TextInput
                            value={skills.discord?.admin_id || ''}
                            onChange={(e) => updateSkill('discord', 'admin_id', e.target.value)}
                            className="font-mono"
                        />
                    </Field>
                </div>
                <Slider
                    label="Interrupt after"
                    value={skills.discord?.interrupt_threshold_ms ?? 3000}
                    onChange={(value) => updateSkill('discord', 'interrupt_threshold_ms', value)}
                    min={1000} max={10000} step={250}
                    format={(v) => `${(v / 1000).toFixed(2)}s`}
                />
                <p className="text-[11px] leading-snug text-faint">
                    How long someone has to keep talking before she stops to listen. Short interjections are
                    buffered instead of cutting her off.
                </p>
            </Group>

            <Group title="Telegram" description="Private conversations that run beside everything else.">
                <CheckRow
                    checked={skills.telegram?.enabled}
                    onChange={(value) => updateSkill('telegram', 'enabled', value)}
                    title="Let her onto Telegram"
                />
                <Field label="Bot token" action={<SecretState configured={secrets['telegram.token']} />}>
                    <SecretInput
                        value={skills.telegram?.token || ''}
                        onChange={(e) => updateSkill('telegram', 'token', e.target.value)}
                    />
                </Field>
                <Field label="Owner id" help="The one chat she treats as her owner.">
                    <TextInput
                        value={skills.telegram?.owner_id || ''}
                        onChange={(e) => updateSkill('telegram', 'owner_id', e.target.value)}
                        className="font-mono"
                    />
                </Field>
            </Group>

            <Group title="Twitch" description="She reads the stream chat and answers what concerns her.">
                <CheckRow
                    checked={skills.twitch?.enabled}
                    onChange={(value) => updateSkill('twitch', 'enabled', value)}
                    title="Let her read the stream chat"
                />
                <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Channel">
                        <TextInput
                            value={skills.twitch?.channel || ''}
                            onChange={(e) => updateSkill('twitch', 'channel', e.target.value)}
                            className="font-mono"
                        />
                    </Field>
                    <Field label="Bot nickname">
                        <TextInput
                            value={skills.twitch?.nick || ''}
                            onChange={(e) => updateSkill('twitch', 'nick', e.target.value)}
                            className="font-mono"
                        />
                    </Field>
                </div>
                <Field label="OAuth token" action={<SecretState configured={secrets['twitch.oauth_token']} />}>
                    <SecretInput
                        value={skills.twitch?.oauth_token || ''}
                        onChange={(e) => updateSkill('twitch', 'oauth_token', e.target.value)}
                        placeholder="oauth:…"
                    />
                </Field>
            </Group>

            <Group title="Donations" description="Alerts reach her as perceptions, so she reacts to them live.">
                <CheckRow
                    checked={skills.donations?.enabled}
                    onChange={(value) => updateSkill('donations', 'enabled', value)}
                    title="Let donations reach her"
                    help="Point your alert service at POST /webhook/donation."
                />
            </Group>
        </>
    );
}

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
                        placeholder="ws://localhost:8080"
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
                <div className="flex items-center justify-between gap-3 rounded-b2 border border-line bg-white/[0.02] p-3">
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

export const SECTIONS = {
    mind: MindSection,
    engine: EngineSection,
    voice: VoiceSection,
    hearing: HearingSection,
    stream: StreamSection,
    channels: ChannelsSection,
    world: WorldSection,
};
