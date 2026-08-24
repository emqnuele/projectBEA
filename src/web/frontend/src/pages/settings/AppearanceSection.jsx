import React from 'react';
import { Check, Moon, RotateCcw, Sun } from 'lucide-react';
import { DEFAULTS, useAppearance } from '../../state/AppearanceProvider';
import { Glass } from '../../components/glass/Glass';
import { Button, Segmented, Switch } from '../../components/ui/controls';
import { Slider } from '../../components/ui/fields';
import { Group } from './parts';

const CONTROLS = [
    {
        key: 'refraction', label: 'Refraction', min: 0, max: 120, step: 1,
        help: 'How far the backdrop bends. This is the difference between glass and frosted plastic.',
        format: (v) => `${Math.round(v)}`,
    },
    {
        key: 'dispersion', label: 'Dispersion', min: 0, max: 80, step: 1,
        help: 'The rainbow fringe at the rim, from the three colour channels bending by different amounts.',
        format: (v) => `${Math.round(v)}`,
    },
    {
        key: 'frost', label: 'Frost', min: 0, max: 48, step: 1,
        help: 'Blur behind the surface.',
        format: (v) => `${Math.round(v)}px`,
    },
    {
        key: 'splay', label: 'Splay', min: 0, max: 0.95, step: 0.01,
        help: 'How far in from the edge the warp reaches. Lower warps the whole pane.',
        format: (v) => `${Math.round(v * 100)}%`,
    },
    {
        key: 'light', label: 'Light', min: 0, max: 1.4, step: 0.02,
        help: 'The specular rim that makes it read as a physical object.',
        format: (v) => v.toFixed(2),
    },
    {
        key: 'depth', label: 'Depth', min: 0, max: 2.2, step: 0.05,
        help: 'How far the surface floats above what is behind it.',
        format: (v) => v.toFixed(2),
    },
    {
        key: 'saturate', label: 'Colour lift', min: 0.6, max: 2.4, step: 0.05,
        help: 'How much colour the surface pulls out of the backdrop.',
        format: (v) => v.toFixed(2),
    },
];

// no orange: the room reads as an instrument, not as a brand
const PRESETS = [
    ['#3d7dff', 'Blue'],
    ['#39c2e6', 'Ice'],
    ['#6f6bff', 'Indigo'],
    ['#a56bff', 'Violet'],
    ['#2fc98d', 'Emerald'],
    ['#ff5c86', 'Rose'],
    ['#c8c8d2', 'Graphite'],
];

const LADDER = [
    ['Speech', 'var(--flux-out)'],
    ['Thought', 'var(--flux-think)'],
    ['Action', 'var(--flux-act)'],
    ['Perception', 'var(--flux-in)'],
    ['Ignored', 'var(--flux-mute)'],
    ['Failure', 'var(--flux-err)'],
];

function AccentPicker({ value, onChange }) {
    const custom = !PRESETS.some(([hex]) => hex.toLowerCase() === value.toLowerCase());

    return (
        <div className="flex flex-wrap items-center gap-2">
            {PRESETS.map(([hex, name]) => {
                const active = hex.toLowerCase() === value.toLowerCase();
                return (
                    <button
                        key={hex}
                        type="button"
                        onClick={() => onChange(hex)}
                        title={name}
                        aria-label={name}
                        aria-pressed={active}
                        className="grid h-8 w-8 place-items-center rounded-full border transition-transform hover:scale-110"
                        style={{
                            background: hex,
                            borderColor: active ? 'var(--text)' : 'transparent',
                            boxShadow: active ? '0 0 0 2px var(--bg), 0 0 0 3px var(--text)' : 'none',
                        }}
                    >
                        {active && <Check size={13} strokeWidth={3} style={{ color: '#0b0b0d' }} />}
                    </button>
                );
            })}

            <label
                className="ml-1 flex cursor-pointer items-center gap-2 rounded-full border border-line px-3 py-1.5 text-[11px] font-medium text-dim transition-colors hover:border-line-strong hover:text-text"
                title="Pick any colour"
            >
                <span
                    className="h-3.5 w-3.5 rounded-full border border-line"
                    style={{ background: custom ? value : 'transparent' }}
                />
                {custom ? value.toUpperCase() : 'Custom'}
                <input
                    type="color"
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    aria-label="Custom accent colour"
                    className="h-0 w-0 opacity-0"
                />
            </label>
        </div>
    );
}

/** Everything else is derived from it, so the ladder always stays coherent. */
function AccentLadder() {
    return (
        <div className="flex flex-wrap gap-x-4 gap-y-2 rounded-b2 border border-line bg-fill p-3">
            {LADDER.map(([label, color]) => (
                <span key={label} className="flex items-center gap-1.5 text-[11px] text-dim">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                    {label}
                </span>
            ))}
        </div>
    );
}

export function AppearanceSection() {
    const { settings, set, reset } = useAppearance();

    return (
        <>
            <Group title="Theme" description="Dark is the default — this sits next to OBS at night.">
                <Segmented
                    value={settings.theme}
                    onChange={(value) => set('theme', value)}
                    options={[
                        { value: 'dark', label: 'Dark', icon: <Moon size={12} /> },
                        { value: 'light', label: 'Light', icon: <Sun size={12} /> },
                    ]}
                />
            </Group>

            <Group
                title="Accent"
                description="The room is black and white. This is the one hue allowed in, and it means one thing: she is awake and doing something."
            >
                <AccentPicker value={settings.accent} onChange={(value) => set('accent', value)} />
                <AccentLadder />
            </Group>

            <Group
                title="Liquid glass"
                description="Every surface in the room is one pane of glass over a moving ground. These are its optics."
            >
                <div className="flex items-center justify-between gap-4 rounded-b2 border border-line bg-fill p-3">
                    <span>
                        <span className="block text-[13px] font-medium text-text">Refract the backdrop</span>
                        <span className="mt-0.5 block text-[11px] leading-snug text-faint">
                            Turn this off on a slow machine — the frost and the rim light stay.
                        </span>
                    </span>
                    <Switch
                        checked={settings.glass}
                        onChange={(value) => set('glass', value)}
                        label="Refract the backdrop"
                    />
                </div>

                <Preview />

                <div className={settings.glass ? '' : 'pointer-events-none opacity-40'}>
                    <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
                        {CONTROLS.map((control) => (
                            <div key={control.key}>
                                <Slider
                                    label={control.label}
                                    value={settings[control.key]}
                                    onChange={(value) => set(control.key, value)}
                                    min={control.min}
                                    max={control.max}
                                    step={control.step}
                                    format={control.format}
                                />
                                <p className="mt-1 text-[11px] leading-snug text-faint">{control.help}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </Group>

            <Group title="Ground" description="Glass needs something behind it worth bending.">
                <div className="flex items-center justify-between gap-4 rounded-b2 border border-line bg-fill p-3">
                    <span>
                        <span className="block text-[13px] font-medium text-text">Dithered backdrop</span>
                        <span className="mt-0.5 block text-[11px] leading-snug text-faint">
                            A slow two-tone field, ordered-dithered rather than smoothly blended.
                        </span>
                    </span>
                    <Switch
                        checked={settings.dither}
                        onChange={(value) => set('dither', value)}
                        label="Dithered backdrop"
                    />
                </div>
                <p className="text-[11px] leading-snug text-faint">
                    Motion is dropped automatically when the system asks for reduced motion.
                </p>
            </Group>

            <div className="flex justify-end">
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={reset}
                    disabled={CONTROLS.every((c) => settings[c.key] === DEFAULTS[c.key])
                        && settings.theme === DEFAULTS.theme
                        && settings.accent === DEFAULTS.accent}
                >
                    <RotateCcw size={13} /> Back to the defaults
                </Button>
            </div>
        </>
    );
}

/** A deliberately busy ground, so a change to any slider is actually visible. */
function Preview() {
    return (
        <div className="relative h-56 overflow-hidden rounded-b3 border border-line">
            <div
                className="absolute inset-0"
                style={{
                    background:
                        'radial-gradient(circle at 22% 30%, var(--accent) 0%, transparent 44%),' +
                        'radial-gradient(circle at 78% 68%, var(--text) 0%, transparent 40%),' +
                        'radial-gradient(circle at 55% 12%, var(--cognition) 0%, transparent 36%),' +
                        'var(--bg-sunken)',
                }}
            />
            <div
                className="absolute inset-0 opacity-45"
                style={{
                    backgroundImage:
                        'repeating-linear-gradient(90deg, transparent 0 11px, rgb(255 255 255 / 22%) 11px 12px),' +
                        'repeating-linear-gradient(0deg, transparent 0 11px, rgb(255 255 255 / 22%) 11px 12px)',
                }}
            />
            <Glass className="absolute inset-x-1/4 inset-y-12 grid place-items-center rounded-b3">
                <p className="font-display text-sm font-semibold text-text">Liquid glass</p>
            </Glass>
        </div>
    );
}
