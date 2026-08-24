import React, { useCallback, useEffect, useId, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { cn } from '../../lib/cn';

const FOCUSABLE =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A real dialog: Escape closes it, focus is trapped inside while it is open and
 * handed back to whatever opened it on the way out.
 */
export function Modal({ open, onClose, title, description, children, footer, size = 'md', labelledBy }) {
    const panelRef = useRef(null);
    const returnFocusTo = useRef(null);
    const headingId = useId();

    const handleKeyDown = useCallback((event) => {
        if (event.key === 'Escape') {
            event.stopPropagation();
            onClose?.();
            return;
        }
        if (event.key !== 'Tab') return;

        const nodes = panelRef.current?.querySelectorAll(FOCUSABLE);
        if (!nodes?.length) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }, [onClose]);

    useEffect(() => {
        if (!open) return undefined;
        returnFocusTo.current = document.activeElement;
        const overflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';

        const timer = setTimeout(() => {
            const nodes = panelRef.current?.querySelectorAll(FOCUSABLE);
            (nodes?.[0] || panelRef.current)?.focus();
        }, 40);

        return () => {
            clearTimeout(timer);
            document.body.style.overflow = overflow;
            returnFocusTo.current?.focus?.();
        };
    }, [open]);

    const width = {
        sm: 'max-w-sm',
        md: 'max-w-lg',
        lg: 'max-w-3xl',
        xl: 'max-w-5xl',
    }[size];

    return (
        <AnimatePresence>
            {open && (
                <motion.div
                    className="fixed inset-0 z-[150] grid place-items-center p-4"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                >
                    <div
                        className="absolute inset-0 bg-black/50 backdrop-blur-[3px]"
                        onClick={onClose}
                        aria-hidden="true"
                    />
                    <motion.div
                        ref={panelRef}
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby={labelledBy || headingId}
                        tabIndex={-1}
                        data-focus-ring="off"
                        onKeyDown={handleKeyDown}
                        initial={{ opacity: 0, y: 14, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 8, scale: 0.985 }}
                        transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                        className={cn(
                            'glass relative flex w-full flex-col overflow-hidden rounded-b4 outline-none',
                            width,
                        )}
                    >
                        <span className="glass-sheen" aria-hidden="true" />
                        {(title || onClose) && (
                            <header className="flex items-start gap-4 border-b border-line px-5 py-4">
                                <div className="min-w-0 flex-1">
                                    {title && (
                                        <h2 id={headingId} className="font-display text-base font-semibold text-text">
                                            {title}
                                        </h2>
                                    )}
                                    {description && <p className="mt-1 text-xs leading-relaxed text-dim">{description}</p>}
                                </div>
                                {onClose && (
                                    <button
                                        onClick={onClose}
                                        aria-label="Close"
                                        className="-m-1.5 rounded-b1 p-1.5 text-faint transition-colors hover:bg-fill-2 hover:text-text"
                                    >
                                        <X size={16} />
                                    </button>
                                )}
                            </header>
                        )}
                        {children && <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>}
                        {footer && (
                            <footer className="flex items-center justify-end gap-2 border-t border-line px-5 py-3.5">
                                {footer}
                            </footer>
                        )}
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
