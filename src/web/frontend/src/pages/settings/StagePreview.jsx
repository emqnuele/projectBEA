import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Eye, MessageCircle, X } from 'lucide-react';
import { api } from '../../api';
import { testEnvelope } from '../../lib/testLine';
import { Group } from './parts';
import { Button, IconButton, Segmented } from '../../components/ui/controls';

/**
 * What the audience will actually see, without opening OBS.
 *
 * For the 3D model the preview is not a mock-up of the browser source: it *is*
 * the browser source, in an iframe. There is no second renderer to keep in
 * sync, and what you approve here is exactly what OBS gets.
 */

const STATES = [
    { value: 'idle', label: 'Idle' },
    { value: 'talking', label: 'Talking' },
];

// the alpha checkerboard: whatever is drawn over this is what OBS composites,
// and everything else the panel is standing in for
const CHECKS = {
    backgroundColor: 'var(--bg-sunken)',
    backgroundImage: [
        'linear-gradient(45deg, var(--fill-3) 25%, transparent 25%)',
        'linear-gradient(-45deg, var(--fill-3) 25%, transparent 25%)',
        'linear-gradient(45deg, transparent 75%, var(--fill-3) 75%)',
        'linear-gradient(-45deg, transparent 75%, var(--fill-3) 75%)',
    ].join(', '),
    backgroundSize: '18px 18px',
    backgroundPosition: '0 0, 0 9px, 9px -9px, -9px 0',
};

function Frame({ children, tall }) {
    return (
        <div
            className="grid place-items-center overflow-hidden rounded-b2 border border-line"
            style={{ ...CHECKS, minHeight: tall ? 420 : 260 }}
        >
            {children}
        </div>
    );
}

function Empty({ icon: Icon = Eye, children }) {
    return (
        <div className="flex max-w-xs flex-col items-center gap-2 p-6 text-center">
            <Icon size={18} className="text-faint" />
            <p className="text-[13px] leading-relaxed text-dim">{children}</p>
        </div>
    );
}

function PngPreview({ map }) {
    const moods = Object.keys(map);
    const [mood, setMood] = useState(moods[0] || 'neutral');
    const [state, setState] = useState('idle');
    const [missing, setMissing] = useState(false);

    // the mapped path rides along so the url changes when the mapping does:
    // the engine serves the same address either way, and the browser caches it
    const file = map[mood]?.[state] || '';
    const src = `/stage/preview?mood=${encodeURIComponent(mood)}`
        + `&state=${state}&file=${encodeURIComponent(file)}`;
    useEffect(() => setMissing(false), [src]);

    return (
        <>
            <div className="flex flex-wrap items-center gap-2">
                <Segmented
                    value={mood}
                    onChange={setMood}
                    options={moods.map((m) => ({ value: m, label: m }))}
                    size="sm"
                />
                <div className="ml-auto">
                    <Segmented
                        value={state}
                        onChange={setState}
                        options={STATES}
                        size="sm"
                    />
                </div>
            </div>
            <Frame>
                {missing ? (
                    <Empty icon={AlertTriangle}>
                        Nothing is mapped for <span className="font-mono text-text">{mood} / {state}</span>,
                        or the file is not on disk.
                    </Empty>
                ) : (
                    <img
                        key={src}
                        src={src}
                        alt={`${mood}, ${state}`}
                        className="max-h-[380px] w-auto object-contain"
                        onError={() => setMissing(true)}
                    />
                )}
            </Frame>
        </>
    );
}

const TRY_STATES = [
    { value: 'idle', label: 'Idle' },
    { value: 'listening', label: 'Listening' },
    { value: 'thinking', label: 'Thinking' },
    { value: 'talking', label: 'Talking' },
    { value: 'sleeping', label: 'Asleep' },
];

// the settings the preview wears before they are saved, so a slider can be judged by eye
const LOOK_KEYS = ['shot', 'background', 'idle_clip', 'state_clips', 'expression_intensity',
    'face_blend_blink', 'mouth_under_emotion'];

function TryPanel({ frame, stage, gestures }) {
    const [ready, setReady] = useState(false);
    const [moods, setMoods] = useState({});
    const [mood, setMood] = useState('neutral');
    const [state, setState] = useState('idle');
    const lineTimer = useRef(null);

    const post = (message) => {
        frame.current?.contentWindow?.postMessage({ type: 'bea-preview', ...message }, window.location.origin);
    };

    useEffect(() => {
        api.stageMoods().then(setMoods).catch(() => setMoods({}));
        const onMessage = (event) => {
            if (event.origin === window.location.origin && event.data?.type === 'bea-preview-ready') setReady(Boolean(event.data.ok));
        };
        window.addEventListener('message', onMessage);
        return () => {
            window.removeEventListener('message', onMessage);
            clearTimeout(lineTimer.current);
        };
    }, []);

    const look = JSON.stringify(Object.fromEntries(LOOK_KEYS.map((k) => [k, stage[k]])));
    useEffect(() => {
        if (!ready) return;
        frame.current?.contentWindow?.postMessage({ type: 'bea-preview', look: JSON.parse(look) }, window.location.origin);
    }, [ready, look, frame]);

    const wear = (name) => {
        setMood(name);
        post({ patch: { mood: name, expressions: moods[name] } });
    };
    const become = (name) => {
        setState(name);
        post({ patch: { state: name } });
    };
    const sayTestLine = () => {
        const fps = 30;
        const frames = testEnvelope(3, fps);
        clearTimeout(lineTimer.current);
        post({ patch: { state: 'talking' } });
        post({ patch: { envelope: frames, envelope_fps: fps } });
        lineTimer.current = setTimeout(() => post({ patch: { state } }), (frames.length / fps) * 1000);
    };

    if (!ready) return <p className="text-[11px] text-faint">Loading the model into the preview…</p>;
    return (
        <div className="space-y-2.5">
            <div className="flex flex-wrap items-center gap-2">
                <Segmented value={state} onChange={become} options={TRY_STATES} size="sm" />
                <Button size="sm" variant="outline" onClick={sayTestLine}>
                    <MessageCircle size={13} /> Say a test line
                </Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
                {Object.keys(moods).map((name) => (
                    <Button key={name} size="sm" variant={name === mood ? 'vital' : 'ghost'} onClick={() => wear(name)}>
                        {name}
                    </Button>
                ))}
            </div>
            {gestures.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                    {gestures.map((name) => (
                        <Button key={name} size="sm" variant="outline" onClick={() => post({ patch: { perform: name } })}>
                            {name}
                        </Button>
                    ))}
                </div>
            )}
            <p className="text-[11px] leading-snug text-faint">
                Only this preview changes: the stream keeps what the engine sends. Unsaved face and framing
                settings show here as you move them.
            </p>
        </div>
    );
}

function ModelPreview({ hasModel, modelPath, previewId, onStopPreview, stage, gestures }) {
    const [trying, setTrying] = useState(false);
    const frame = useRef(null);
    const target = previewId || (trying ? 'active' : null);

    if (!hasModel && !previewId) {
        return (
            <Frame>
                <Empty>
                    Choose a model in the library below, or get the free one. No model ships with
                    projectBEA, and <span className="font-mono text-text">make model</span> fetches the same free one.
                </Empty>
            </Frame>
        );
    }
    return (
        <>
            <div className="flex flex-wrap items-center gap-2">
                {previewId ? (
                    <>
                        <p className="min-w-0 flex-1 truncate text-[12px] text-dim">
                            Previewing <span className="font-mono text-text">{previewId}</span>, not on stage
                        </p>
                        <IconButton size="sm" label="Close the preview" onClick={onStopPreview}><X size={14} /></IconButton>
                    </>
                ) : (
                    <Segmented
                        value={trying ? 'try' : 'live'}
                        onChange={(v) => setTrying(v === 'try')}
                        options={[{ value: 'live', label: 'What the stream sees' }, { value: 'try', label: 'Try things on' }]}
                        size="sm"
                    />
                )}
            </div>
            {/* the page paints nothing but her, so the iframe must not lay its own opaque white underneath it */}
            <div className="overflow-hidden rounded-b2 border border-line" style={CHECKS}>
                <iframe
                    ref={frame}
                    key={`${target || 'live'}:${modelPath}`}
                    title={target ? 'Model preview' : 'The browser source'}
                    src={target ? `/stage?hud=0&preview=${encodeURIComponent(target)}` : '/stage?hud=0'}
                    className="block h-[420px] w-full border-0"
                    style={{ background: 'transparent', colorScheme: 'normal' }}
                />
            </div>
            {target ? (
                <TryPanel key={target} frame={frame} stage={stage} gestures={gestures} />
            ) : (
                <p className="text-[11px] leading-snug text-faint">
                    This is the browser source itself, not a mock-up. The chequerboard is this
                    panel showing through — OBS composites her over your scene instead.
                    Saving a change here updates it live.
                </p>
            )}
        </>
    );
}

function VtsPreview({ status }) {
    return (
        <Frame>
            <Empty>
                {status?.ok
                    ? <>Connected to <span className="font-mono text-text">{status.model || 'VTube Studio'}</span>. The
                        model is drawn by VTube Studio itself, so preview it in its own window.</>
                    : <>VTube Studio renders in its own window, so there is nothing to show here.
                        Use <span className="font-mono text-text">Test the connection</span> below to check she can reach it.</>}
            </Empty>
        </Frame>
    );
}

export function StagePreview({ config, vtsStatus, previewId, onStopPreview, gestures = [] }) {
    const stage = config.stage || {};
    const backend = stage.avatar_backend || 'png';

    return (
        <Group title="Preview" description="What the stream sees, before you go looking in OBS.">
            {backend === 'png' && <PngPreview map={config.avatar_map || {}} />}
            {backend === 'model' && (
                <ModelPreview
                    hasModel={Boolean(stage.model_path)}
                    modelPath={stage.model_path}
                    previewId={previewId}
                    onStopPreview={onStopPreview}
                    stage={stage}
                    gestures={gestures}
                />
            )}
            {backend === 'vtube_studio' && <VtsPreview status={vtsStatus} />}
        </Group>
    );
}
