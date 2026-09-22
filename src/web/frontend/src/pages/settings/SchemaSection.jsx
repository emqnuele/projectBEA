import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, RotateCcw, Save } from 'lucide-react';
import { api } from '../../api';
import { Glass } from '../../components/glass/Glass';
import { Button, Switch } from '../../components/ui/controls';
import { CheckRow, Field, SecretInput, Select, Slider, TextInput } from '../../components/ui/fields';
import { Skeleton } from '../../components/ui/feedback';
import { windowShape } from '../../lib/budget';
import { compact } from '../../lib/format';
import { useToast } from '../../state/ToastProvider';
import { Group } from './parts';

const MASK = '********';

/**
 * A settings screen the engine describes, rather than one written by hand.
 *
 * Every knob Bea has is declared once on the server; this renders whatever
 * comes back. Adding a setting is a line of Python — it shows up here typed,
 * explained and validated, instead of quietly living in config.json forever.
 */

// "channel: expected a number; nope: unknown setting" -> { channel, nope }
function fieldErrors(detail) {
    const out = {};
    String(detail || '').split(';').forEach((part) => {
        const [key, ...rest] = part.split(':');
        if (key && rest.length) out[key.trim()] = rest.join(':').trim();
    });
    return out;
}

function asList(value) {
    return Array.isArray(value) ? value.join(', ') : (value ?? '');
}

function Control({ setting, value, onChange, error }) {
    const common = { id: setting.key, 'aria-invalid': error ? true : undefined };

    switch (setting.type) {
        case 'bool':
            return (
                <CheckRow
                    checked={value}
                    onChange={onChange}
                    title={setting.label}
                    help={setting.help}
                />
            );
        case 'secret':
            return (
                <SecretInput
                    {...common}
                    value={value === MASK ? '' : (value ?? '')}
                    placeholder={value === MASK ? 'A token is stored' : 'Not set'}
                    onChange={(e) => onChange(e.target.value)}
                />
            );
        case 'select':
            return (
                <Select {...common} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
                    {(setting.options || []).map((option) => (
                        <option key={option} value={option}>{option}</option>
                    ))}
                </Select>
            );
        case 'float':
            return (
                <Slider
                    label={setting.label}
                    value={Number(value ?? setting.default ?? 0)}
                    min={setting.min ?? 0}
                    max={setting.max ?? 1}
                    step={0.05}
                    onChange={onChange}
                    format={(v) => v.toFixed(2)}
                />
            );
        case 'int':
            if (setting.ui === 'slider') {
                return (
                    <Slider
                        label={setting.label}
                        value={Number(value ?? setting.default ?? 0)}
                        min={setting.min ?? 0}
                        max={setting.max ?? 100}
                        step={setting.step ?? 1}
                        onChange={(v) => onChange(Math.round(v))}
                        format={compact}
                    />
                );
            }
            return (
                <TextInput
                    {...common}
                    type="number"
                    inputMode="numeric"
                    min={setting.min ?? undefined}
                    max={setting.max ?? undefined}
                    value={value ?? ''}
                    onChange={(e) => onChange(e.target.value)}
                    className="tnum font-mono"
                />
            );
        case 'list':
            return (
                <TextInput
                    {...common}
                    value={asList(value)}
                    placeholder="comma separated"
                    onChange={(e) => onChange(e.target.value)}
                />
            );
        default:
            return (
                <TextInput
                    {...common}
                    value={value ?? ''}
                    onChange={(e) => onChange(e.target.value)}
                />
            );
    }
}

/** The on/off switch is not a field: it starts and stops a live connection. */
function LiveSwitch({ label, checked, onChange, busy }) {
    return (
        <Glass quiet className="mb-2.5 flex items-center justify-between gap-4 rounded-b3 p-4 sm:p-5">
            <div className="min-w-0">
                <h2 className="font-display text-[13px] font-semibold text-text">
                    {checked ? `${label} is on` : `${label} is off`}
                </h2>
                <p className="mt-1 text-[11px] leading-snug text-faint">
                    {checked
                        ? 'She is connected and reading. Turning this off disconnects her right away.'
                        : 'Nothing is connected. Turn it on once the settings below are filled in.'}
                </p>
            </div>
            <Switch checked={checked} onChange={onChange} label={label} disabled={busy} />
        </Glass>
    );
}

export function createSchemaSection(sectionKey) {
    function SchemaSection() {
        const [schema, setSchema] = useState(null);
        const [values, setValues] = useState({});
        const [saved, setSaved] = useState('');
        const [errors, setErrors] = useState({});
        const [saving, setSaving] = useState(false);
        const toast = useToast();
        const mounted = useRef(true);

        const load = useCallback(async () => {
            try {
                const data = await api.settingsSection(sectionKey);
                if (!mounted.current) return;
                setSchema(data);
                setValues(data.values);
                setSaved(JSON.stringify(data.values));
                setErrors({});
            } catch (e) {
                toast.error('Could not read these settings', e.message);
            }
        }, [toast]);

        useEffect(() => {
            mounted.current = true;
            load();
            return () => { mounted.current = false; };
        }, [load]);

        const dirty = useMemo(
            () => Boolean(saved && JSON.stringify(values) !== saved),
            [values, saved],
        );

        const set = (key, value) => {
            setValues((prev) => ({ ...prev, [key]: value }));
            setErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev));
        };

        const persist = async (patch) => {
            setSaving(true);
            try {
                const result = await api.saveSettings(sectionKey, patch);
                const next = { ...values, ...patch };
                setValues(next);
                setSaved(JSON.stringify(next));
                setErrors({});
                if (result.restart_required) {
                    toast.info('Saved — restart to apply', 'Some of this only takes effect on a restart.');
                } else {
                    toast.success('Saved', 'She is already using it.');
                }
                // a secret comes back masked, and the switch may have started a
                // connection: read the truth rather than assume it
                await load();
                return true;
            } catch (e) {
                const mapped = fieldErrors(e.message);
                if (Object.keys(mapped).length) {
                    setErrors(mapped);
                    toast.error('Nothing was saved', 'Check the fields marked below.');
                } else {
                    toast.error('Nothing was saved', e.message);
                }
                return false;
            } finally {
                setSaving(false);
            }
        };

        const save = () => {
            // masked secrets are dropped: sending them back would store asterisks
            const patch = {};
            Object.entries(values).forEach(([key, value]) => {
                if (value !== MASK) patch[key] = value;
            });
            return persist(patch);
        };

        const discard = () => {
            setValues(JSON.parse(saved));
            setErrors({});
        };

        if (!schema) {
            return (
                <div className="space-y-3">
                    <Skeleton className="h-20" />
                    <Skeleton className="h-52" />
                </div>
            );
        }

        const toggle = schema.toggleable ? schema.settings.find((s) => s.key === 'enabled') : null;
        const fields = schema.settings.filter((s) => s !== toggle);
        const plain = fields.filter((s) => !s.advanced);
        const advanced = fields.filter((s) => s.advanced);
        const needsRestart = fields.some((s) => s.restart && errors[s.key] === undefined);

        // a control that carries its own label is not wrapped in a Field, or
        // the label is drawn twice
        const selfLabelled = (s) => s.type === 'bool' || s.type === 'float' || s.ui === 'slider';

        const renderField = (setting) => (
            selfLabelled(setting) ? (
                <div key={setting.key} className="space-y-1.5">
                    <Control
                        setting={setting}
                        value={values[setting.key]}
                        onChange={(v) => set(setting.key, v)}
                        error={errors[setting.key]}
                    />
                    {setting.derives?.length > 0 && (
                        <DerivedShape
                            setting={setting}
                            ceiling={values[setting.key]}
                            values={values}
                        />
                    )}
                    {setting.type !== 'bool' && (
                        <p className="text-[11px] leading-snug text-faint">{setting.help}</p>
                    )}
                    {errors[setting.key] && <FieldError text={errors[setting.key]} />}
                </div>
            ) : (
                <Field
                    key={setting.key}
                    label={setting.label}
                    htmlFor={setting.key}
                    help={setting.help}
                    error={errors[setting.key]}
                    action={setting.restart ? <RestartTag /> : null}
                >
                    <Control
                        setting={setting}
                        value={values[setting.key]}
                        onChange={(v) => set(setting.key, v)}
                        error={errors[setting.key]}
                    />
                </Field>
            )
        );

        return (
            <>
                {toggle && (
                    <LiveSwitch
                        label={schema.label}
                        checked={Boolean(values.enabled)}
                        busy={saving}
                        onChange={(next) => persist({ enabled: next })}
                    />
                )}

                <Group title="Settings" description={schema.blurb}>
                    {plain.map(renderField)}
                </Group>

                {advanced.length > 0 && (
                    <details className="group mt-2.5">
                        <summary className="cursor-pointer list-none px-1 text-[11px] font-semibold uppercase tracking-wider text-faint transition-colors hover:text-dim">
                            Advanced — {advanced.length} more
                        </summary>
                        <div className="mt-2.5">
                            <Group
                                title="Advanced"
                                description="Numbers the settings above already work out. Set one and it stops following them."
                            >
                                {advanced.map(renderField)}
                            </Group>
                        </div>
                    </details>
                )}

                {needsRestart && (
                    <p className="px-1 text-[11px] leading-snug text-faint">
                        Fields marked <span className="font-mono uppercase tracking-wider">restart</span> only
                        take effect after the engine is restarted.
                    </p>
                )}

                <AnimatePresence>
                    {dirty && (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 20 }}
                            transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                            className="pointer-events-none fixed inset-x-0 bottom-4 z-40 flex justify-center px-4"
                        >
                            <Glass className="pointer-events-auto flex items-center gap-3 rounded-full py-2 pl-5 pr-2">
                                <span className="text-[13px] text-dim">Unsaved changes</span>
                                <Button variant="ghost" size="sm" onClick={discard}>
                                    <RotateCcw size={13} /> Discard
                                </Button>
                                <Button variant="primary" size="sm" onClick={save} loading={saving}>
                                    <Save size={13} /> Save
                                </Button>
                            </Glass>
                        </motion.div>
                    )}
                </AnimatePresence>
            </>
        );
    }

    SchemaSection.displayName = `SchemaSection(${sectionKey})`;
    return SchemaSection;
}

/**
 * What the number above it works out to everywhere else.
 *
 * Without this the slider is a single opaque figure: the one that decides how
 * much she actually keeps is the handoff trigger, and it moves with the
 * ceiling rather than being the ceiling. A value pinned in Advanced says so
 * here, so a slider that is only moving part of the window cannot look like
 * it is moving all of it.
 */
function DerivedShape({ setting, ceiling, values }) {
    const shape = windowShape(Number(ceiling ?? setting.default ?? 0), setting.derives, values);
    return (
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-0.5 text-[11px] text-faint">
            {shape.map(({ key, label, tokens, pinned }) => (
                <span key={key}>
                    {label}{' '}
                    <span className="tnum font-mono text-dim">{compact(tokens)}</span>
                    {pinned && <span className="ml-1 uppercase tracking-wider">pinned</span>}
                </span>
            ))}
        </p>
    );
}

function FieldError({ text }) {
    return (
        <p className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--flux-err)' }}>
            <AlertTriangle size={11} className="shrink-0" />
            {text}
        </p>
    );
}

function RestartTag() {
    return <span className="font-mono text-[10px] uppercase tracking-wider text-faint">restart</span>;
}
