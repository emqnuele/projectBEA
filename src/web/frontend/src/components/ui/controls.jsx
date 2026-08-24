import React, { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/cn';

const VARIANTS = {
    primary: 'bg-text text-bg hover:opacity-90 border border-transparent',
    glass: 'glass-quiet text-text hover:border-line-strong',
    ghost: 'text-dim hover:text-text hover:bg-white/5 border border-transparent',
    outline: 'border border-line text-text hover:border-line-strong hover:bg-white/5',
    danger: 'border text-[color:var(--flux-err)] hover:brightness-110',
    // reserved: only for the controls that act on her being live
    vital: 'border text-[color:var(--vital)] hover:brightness-110',
};

const TINT = {
    danger: { background: 'color-mix(in srgb, var(--flux-err) 12%, transparent)', borderColor: 'color-mix(in srgb, var(--flux-err) 34%, transparent)' },
    vital: { background: 'var(--vital-soft)', borderColor: 'color-mix(in srgb, var(--vital) 38%, transparent)' },
};

const SIZES = {
    sm: 'h-8 px-3 text-xs gap-1.5 rounded-b1',
    md: 'h-9 px-4 text-[13px] gap-2 rounded-b2',
    lg: 'h-11 px-5 text-sm gap-2.5 rounded-b2',
};

export const Button = forwardRef(function Button(
    { variant = 'glass', size = 'md', loading, className, children, disabled, ...props },
    ref,
) {
    return (
        <button
            ref={ref}
            disabled={disabled || loading}
            style={TINT[variant]}
            className={cn(
                'inline-flex shrink-0 select-none items-center justify-center font-semibold transition-all duration-150',
                'disabled:pointer-events-none disabled:opacity-40 active:scale-[0.98]',
                VARIANTS[variant], SIZES[size], className,
            )}
            {...props}
        >
            {loading && <Loader2 size={14} className="animate-spin" />}
            {children}
        </button>
    );
});

export const IconButton = forwardRef(function IconButton(
    { label, variant = 'ghost', size = 'md', className, children, ...props },
    ref,
) {
    const box = { sm: 'h-7 w-7 rounded-b1', md: 'h-9 w-9 rounded-b2', lg: 'h-11 w-11 rounded-b2' }[size];
    return (
        <button
            ref={ref}
            title={label}
            aria-label={label}
            style={TINT[variant]}
            className={cn(
                'inline-grid shrink-0 place-items-center transition-all duration-150',
                'disabled:pointer-events-none disabled:opacity-40 active:scale-95',
                VARIANTS[variant], box, className,
            )}
            {...props}
        >
            {children}
        </button>
    );
});

export function Switch({ checked, onChange, label, disabled }) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={Boolean(checked)}
            aria-label={label}
            disabled={disabled}
            onClick={() => onChange?.(!checked)}
            className={cn(
                'relative h-[22px] w-[38px] shrink-0 rounded-full border transition-colors duration-200',
                'disabled:pointer-events-none disabled:opacity-40',
                checked ? 'border-transparent' : 'border-line bg-white/5',
            )}
            style={checked ? { background: 'var(--vital)' } : undefined}
        >
            <motion.span
                layout
                transition={{ type: 'spring', stiffness: 620, damping: 38 }}
                className={cn(
                    'absolute top-1/2 block h-[16px] w-[16px] -translate-y-1/2 rounded-full',
                    checked ? 'left-[19px] bg-bg' : 'left-[2px] bg-dim',
                )}
            />
        </button>
    );
}

/** A row of exclusive choices. Used wherever a dropdown would be overkill. */
export function Segmented({ value, onChange, options, size = 'md', className }) {
    const pad = size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-3 py-1.5 text-xs';
    return (
        <div className={cn('inline-flex rounded-b2 border border-line bg-white/[0.03] p-0.5', className)} role="tablist">
            {options.map((option) => {
                const active = option.value === value;
                return (
                    <button
                        key={option.value}
                        role="tab"
                        aria-selected={active}
                        onClick={() => onChange?.(option.value)}
                        className={cn(
                            'relative rounded-[calc(var(--r-2)-2px)] font-semibold transition-colors',
                            pad, active ? 'text-text' : 'text-faint hover:text-dim',
                        )}
                    >
                        {active && (
                            <motion.span
                                layoutId={`segmented-${options.map((o) => o.value).join('-')}`}
                                className="absolute inset-0 rounded-[calc(var(--r-2)-2px)] border border-line bg-white/[0.07]"
                                transition={{ type: 'spring', stiffness: 520, damping: 40 }}
                            />
                        )}
                        <span className="relative flex items-center gap-1.5">
                            {option.icon}
                            {option.label}
                        </span>
                    </button>
                );
            })}
        </div>
    );
}
