import React, { useEffect, useState } from 'react';
import { AlertTriangle, Eye } from 'lucide-react';
import { Group } from './parts';
import { Segmented } from '../../components/ui/controls';

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
    const [mood, setMood] = useState(moods[0] || 'normal');
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

function ModelPreview({ hasModel }) {
    if (!hasModel) {
        return (
            <Frame>
                <Empty>
                    Point <span className="font-mono text-text">Model file</span> at a .vrm below.
                    No model ships with projectBEA — run <span className="font-mono text-text">make model</span> for
                    the free sample, or bring your own.
                </Empty>
            </Frame>
        );
    }
    return (
        <>
            {/* the page paints nothing but her, so the iframe must not lay its
                own opaque white underneath it */}
            <div className="overflow-hidden rounded-b2 border border-line" style={CHECKS}>
                <iframe
                    title="The browser source"
                    src="/stage?hud=0"
                    className="block h-[420px] w-full border-0"
                    style={{ background: 'transparent', colorScheme: 'normal' }}
                />
            </div>
            <p className="text-[11px] leading-snug text-faint">
                This is the browser source itself, not a mock-up. The chequerboard is this
                panel showing through — OBS composites her over your scene instead.
                Saving a change here updates it live.
            </p>
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

export function StagePreview({ config, vtsStatus }) {
    const stage = config.stage || {};
    const backend = stage.avatar_backend || 'png';

    return (
        <Group title="Preview" description="What the stream sees, before you go looking in OBS.">
            {backend === 'png' && <PngPreview map={config.avatar_map || {}} />}
            {backend === 'model' && <ModelPreview hasModel={Boolean(stage.model_path)} />}
            {backend === 'vtube_studio' && <VtsPreview status={vtsStatus} />}
        </Group>
    );
}
