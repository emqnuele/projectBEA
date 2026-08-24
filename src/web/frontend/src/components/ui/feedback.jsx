import React from 'react';
import { cn } from '../../lib/cn';

export function Badge({ children, color, className, dot }) {
    return (
        <span
            className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5',
                'font-mono text-[10px] font-semibold uppercase tracking-wider',
                className,
            )}
            style={color ? {
                color,
                borderColor: `color-mix(in srgb, ${color} 34%, transparent)`,
                background: `color-mix(in srgb, ${color} 12%, transparent)`,
            } : { color: 'var(--text-dim)', borderColor: 'var(--line)' }}
        >
            {dot && <span className="h-1.5 w-1.5 rounded-full" style={{ background: color || 'currentColor' }} />}
            {children}
        </span>
    );
}

/** An empty screen is an invitation to act, so it always carries the action. */
export function EmptyState({ icon: Icon, title, children, action, className }) {
    return (
        <div className={cn('flex flex-col items-center justify-center px-6 py-14 text-center', className)}>
            {Icon && (
                <span className="mb-4 grid h-11 w-11 place-items-center rounded-b2 border border-line bg-white/[0.03] text-faint">
                    <Icon size={19} />
                </span>
            )}
            <p className="font-display text-[15px] font-semibold text-text">{title}</p>
            {children && <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-dim">{children}</p>}
            {action && <div className="mt-5">{action}</div>}
        </div>
    );
}

export function Skeleton({ className }) {
    return <div className={cn('shimmer rounded-b2 border border-line bg-white/[0.03]', className)} />;
}

export function Spinner({ size = 16, className }) {
    return (
        <span
            className={cn('inline-block animate-spin rounded-full border-2 border-line', className)}
            style={{ width: size, height: size, borderTopColor: 'var(--text-dim)' }}
            role="progressbar"
            aria-label="Loading"
        />
    );
}
