import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Copy, X } from 'lucide-react';
import { cn } from '../../lib/cn';
import { Glass } from '../../components/glass/Glass';
import { Button } from '../../components/ui/controls';
import { Field, Select, TextInput } from '../../components/ui/fields';
import { chosenDevice, deviceChoices, deviceFor, latencyNote } from '../../lib/audioDevices';
import { useToast } from '../../state/ToastProvider';

export function Group({ title, description, children, className }) {
    return (
        <Glass quiet className={cn('mb-2.5 rounded-b3 p-4 sm:p-5', className)}>
            {title && (
                <div className="mb-4">
                    <h2 className="font-display text-[13px] font-semibold text-text">{title}</h2>
                    {description && <p className="mt-1 text-[11px] leading-snug text-faint">{description}</p>}
                </div>
            )}
            <div className="space-y-4">{children}</div>
        </Glass>
    );
}

/** Choosing a provider is choosing a trade-off, so each card says what it costs. */
export function ProviderChoice({ value, onChange, options, columns = 2 }) {
    return (
        <div className={cn('grid gap-2.5', columns === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}>
            {options.map((option) => {
                const active = option.id === value;
                return (
                    <button
                        key={option.id}
                        type="button"
                        onClick={() => onChange(option.id)}
                        aria-pressed={active}
                        className={cn(
                            'relative rounded-b2 border p-3 text-left transition-all',
                            active ? 'border-transparent' : 'border-line hover:border-line-strong',
                        )}
                        style={active ? {
                            background: 'var(--vital-soft)',
                            boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--vital) 45%, transparent)',
                        } : undefined}
                    >
                        <span className="flex items-center gap-2">
                            <span className={cn('text-[13px] font-semibold', active ? 'text-text' : 'text-dim')}>
                                {option.label}
                            </span>
                            {active && (
                                <Check size={13} className="ml-auto shrink-0" style={{ color: 'var(--vital)' }} />
                            )}
                        </span>
                        <span className="mt-1 block text-[11px] leading-snug text-faint">{option.blurb}</span>
                    </button>
                );
            })}
        </div>
    );
}

/** A secret is either set or not — the value never comes back from the server. */
export function SecretState({ configured, envHint }) {
    return (
        <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider">
            <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ background: configured ? 'var(--flux-act)' : 'var(--flux-err)' }}
            />
            <span style={{ color: configured ? 'var(--flux-act)' : 'var(--flux-err)' }}>
                {configured ? 'set' : 'missing'}
            </span>
            {envHint && <span className="text-faint">· {envHint}</span>}
        </span>
    );
}

/** Does this actually work? A settings page that cannot answer that is a form. */
export function TestButton({ label, run }) {
    const [result, setResult] = useState(null);
    const [busy, setBusy] = useState(false);
    const toast = useToast();

    const probe = async () => {
        setBusy(true);
        setResult(null);
        try {
            const outcome = await run();
            setResult(outcome);
        } catch (e) {
            toast.error('The test could not run', e.message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" variant="outline" onClick={probe} loading={busy}>{label}</Button>
            <AnimatePresence>
                {result && (
                    <motion.span
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0 }}
                        className="flex min-w-0 items-center gap-2 text-[11px]"
                        style={{ color: result.ok ? 'var(--flux-act)' : 'var(--flux-err)' }}
                    >
                        {result.ok ? <Check size={12} /> : <X size={12} />}
                        <span className="truncate">{result.message}</span>
                    </motion.span>
                )}
            </AnimatePresence>
        </div>
    );
}

/** A value you are meant to paste somewhere else, with one click to take it. */
export function CopyField({ value, help }) {
    const toast = useToast();
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(value);
            toast.success('Copied');
        } catch {
            // a browser that refuses the clipboard still lets you select the text
            toast.error('Could not copy — select it and copy by hand');
        }
    };
    return (
        <div>
            <div className="flex items-center gap-2 rounded-b2 border border-line bg-fill px-3 py-2">
                <code className="flex-1 truncate font-mono text-[12px] text-text">{value}</code>
                <Button variant="ghost" size="sm" onClick={copy} aria-label="Copy">
                    <Copy size={13} />
                </Button>
            </div>
            {help && <p className="mt-1.5 text-[11px] leading-snug text-faint">{help}</p>}
        </div>
    );
}

export function OutputDevice({ config, update, devices }) {
    const choices = deviceChoices(devices);
    const chosen = chosenDevice(config, devices);
    const landing = deviceFor(chosen, choices);
    const fallback = choices.find((device) => device.default);
    // stored by name: a position moves whenever something is plugged in
    const choose = (name) => {
        update('audio_device', name);
        update('audio_device_id', null);
    };
    const missing = chosen && !landing;
    return (
        <Field
            label="Output device"
            help={missing
                ? `${chosen} is not plugged in right now: she speaks on the system default until it is.`
                : latencyNote(landing)}
        >
            {choices.length > 0 ? (
                <Select value={chosen} onChange={(e) => choose(e.target.value)}>
                    <option value="">
                        System default{fallback ? ` (${fallback.name})` : ''}
                    </option>
                    {missing && <option value={chosen}>{chosen} (not plugged in)</option>}
                    {choices.map((device) => (
                        <option key={device.name} value={device.name}>{device.name}</option>
                    ))}
                </Select>
            ) : (
                <TextInput
                    value={config.audio_device ?? ''}
                    placeholder="System default"
                    onChange={(e) => choose(e.target.value)}
                />
            )}
        </Field>
    );
}
