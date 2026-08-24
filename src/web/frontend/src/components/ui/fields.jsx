import React, { forwardRef, useId } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { cn } from '../../lib/cn';

const BASE =
    'w-full rounded-b2 border border-line bg-fill px-3 py-2 text-[13px] text-text ' +
    'placeholder:text-faint transition-colors outline-none ' +
    'disabled:opacity-40';

/**
 * Label, control, help and error in one place. The old settings page repeated
 * the same twelve utility classes around thirty bare inputs.
 */
export function Field({ label, help, error, children, htmlFor, className, action }) {
    return (
        <div className={cn('space-y-1.5', className)}>
            {(label || action) && (
                <div className="flex items-baseline justify-between gap-3">
                    {label && (
                        <label htmlFor={htmlFor} className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                            {label}
                        </label>
                    )}
                    {action}
                </div>
            )}
            {children}
            {error ? (
                <p className="text-[11px] leading-snug" style={{ color: 'var(--flux-err)' }}>{error}</p>
            ) : help ? (
                <p className="text-[11px] leading-snug text-faint">{help}</p>
            ) : null}
        </div>
    );
}

export const TextInput = forwardRef(function TextInput({ className, ...props }, ref) {
    return <input ref={ref} className={cn(BASE, className)} {...props} />;
});

export const TextArea = forwardRef(function TextArea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(BASE, 'resize-y leading-relaxed', className)} {...props} />;
});

export const Select = forwardRef(function Select({ className, children, ...props }, ref) {
    return (
        <select ref={ref} className={cn(BASE, 'appearance-none pr-8', className)} {...props}>
            {children}
        </select>
    );
});

/** A secret already stored comes back masked; typing over it replaces it. */
export function SecretInput({ value, onChange, placeholder, configured, ...props }) {
    const [revealed, setRevealed] = React.useState(false);
    const id = useId();
    return (
        <div className="relative">
            <input
                id={id}
                type={revealed ? 'text' : 'password'}
                value={value ?? ''}
                onChange={onChange}
                placeholder={placeholder}
                autoComplete="off"
                spellCheck="false"
                className={cn(BASE, 'pr-10 font-mono')}
                {...props}
            />
            <button
                type="button"
                onClick={() => setRevealed((v) => !v)}
                aria-label={revealed ? 'Hide' : 'Show'}
                className="absolute right-1 top-1/2 -translate-y-1/2 rounded-b1 p-2 text-faint transition-colors hover:text-text"
            >
                {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
            {configured && (
                <span className="mt-1.5 block text-[11px] text-faint">
                    A key is already stored. Type a new one to replace it.
                </span>
            )}
        </div>
    );
}

export function Slider({ value, onChange, min = 0, max = 1, step = 0.01, label, format, className }) {
    const id = useId();
    const pct = ((value - min) / (max - min)) * 100;
    return (
        <div className={cn('space-y-1.5', className)}>
            <div className="flex items-baseline justify-between">
                <label htmlFor={id} className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                    {label}
                </label>
                <span className="tnum font-mono text-[11px] text-faint">
                    {format ? format(value) : value}
                </span>
            </div>
            <input
                id={id}
                type="range"
                min={min}
                max={max}
                step={step}
                value={value}
                onChange={(e) => onChange?.(parseFloat(e.target.value))}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none
                           [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5
                           [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full
                           [&::-webkit-slider-thumb]:bg-text [&::-webkit-slider-thumb]:shadow
                           [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5
                           [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:rounded-full
                           [&::-moz-range-thumb]:bg-text"
                style={{
                    background: `linear-gradient(90deg, var(--text) ${pct}%, var(--line) ${pct}%)`,
                }}
            />
        </div>
    );
}

export function CheckRow({ checked, onChange, title, help }) {
    const id = useId();
    return (
        <label
            htmlFor={id}
            className="flex cursor-pointer items-start gap-3 rounded-b2 border border-line bg-fill p-3 transition-colors hover:border-line-strong"
        >
            <input
                id={id}
                type="checkbox"
                checked={Boolean(checked)}
                onChange={(e) => onChange?.(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 accent-[color:var(--vital)]"
            />
            <span className="min-w-0">
                <span className="block text-[13px] font-medium text-text">{title}</span>
                {help && <span className="mt-0.5 block text-[11px] leading-snug text-faint">{help}</span>}
            </span>
        </label>
    );
}
