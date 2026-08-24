import React from 'react';
import { Moon, RotateCcw, Sun } from 'lucide-react';
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
                        && settings.theme === DEFAULTS.theme}
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
                        'radial-gradient(circle at 22% 30%, var(--vital) 0%, transparent 42%),' +
                        'radial-gradient(circle at 78% 68%, var(--cognition) 0%, transparent 46%),' +
                        'radial-gradient(circle at 55% 15%, var(--flux-in) 0%, transparent 38%),' +
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
