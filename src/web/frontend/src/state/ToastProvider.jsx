import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, Check, Info, X } from 'lucide-react';

const ToastContext = createContext(null);

export function useToast() {
    const value = useContext(ToastContext);
    if (!value) throw new Error('useToast must be used inside <ToastProvider>');
    return value;
}

const TONE = {
    success: { icon: Check, color: 'var(--flux-act)' },
    error: { icon: AlertTriangle, color: 'var(--flux-err)' },
    info: { icon: Info, color: 'var(--flux-in)' },
};

/** Confirmation used to be a modal you had to dismiss. Now it just passes by. */
export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);
    const nextId = useRef(1);

    const dismiss = useCallback((id) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const push = useCallback((toast) => {
        const id = nextId.current++;
        setToasts((prev) => [...prev.slice(-3), { id, tone: 'info', ...toast }]);
        if (toast.tone !== 'error') {
            setTimeout(() => dismiss(id), toast.duration ?? 3800);
        }
        return id;
    }, [dismiss]);

    const value = useMemo(() => ({
        push,
        dismiss,
        success: (title, detail) => push({ tone: 'success', title, detail }),
        error: (title, detail) => push({ tone: 'error', title, detail }),
        info: (title, detail) => push({ tone: 'info', title, detail }),
    }), [push, dismiss]);

    return (
        <ToastContext.Provider value={value}>
            {children}
            <div
                className="pointer-events-none fixed bottom-4 right-4 z-[200] flex w-[min(92vw,22rem)] flex-col gap-2"
                role="status"
                aria-live="polite"
            >
                <AnimatePresence initial={false}>
                    {toasts.map((toast) => {
                        const tone = TONE[toast.tone] || TONE.info;
                        const Icon = tone.icon;
                        return (
                            <motion.div
                                key={toast.id}
                                layout
                                initial={{ opacity: 0, y: 12, scale: 0.97 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                exit={{ opacity: 0, y: 6, scale: 0.97 }}
                                transition={{ type: 'spring', stiffness: 460, damping: 34 }}
                                className="glass-quiet pointer-events-auto flex items-start gap-3 rounded-b2 p-3"
                            >
                                <span
                                    className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full"
                                    style={{ background: `color-mix(in srgb, ${tone.color} 18%, transparent)`, color: tone.color }}
                                >
                                    <Icon size={12} strokeWidth={2.6} />
                                </span>
                                <div className="min-w-0 flex-1">
                                    <p className="text-[13px] font-semibold leading-tight text-text">{toast.title}</p>
                                    {toast.detail && (
                                        <p className="mt-1 break-words text-xs leading-snug text-dim">{toast.detail}</p>
                                    )}
                                </div>
                                <button
                                    onClick={() => dismiss(toast.id)}
                                    aria-label="Dismiss"
                                    className="-m-1 rounded-b1 p-1 text-faint transition-colors hover:text-text"
                                >
                                    <X size={13} />
                                </button>
                            </motion.div>
                        );
                    })}
                </AnimatePresence>
            </div>
        </ToastContext.Provider>
    );
}
