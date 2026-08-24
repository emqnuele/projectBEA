import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { Modal } from '../components/ui/Modal';
import { Button } from '../components/ui/controls';

const DialogContext = createContext(null);

export function useDialog() {
    const value = useContext(DialogContext);
    if (!value) throw new Error('useDialog must be used inside <DialogProvider>');
    return value;
}

const EMPTY = { open: false, title: '', message: '', confirmLabel: 'Confirm', danger: false };

/**
 * Only confirmations live here now — a dialog that exists to say "saved" is a
 * blocking modal for a non-event, so those became toasts.
 */
export function DialogProvider({ children }) {
    const [dialog, setDialog] = useState(EMPTY);
    const resolver = useRef(null);

    const settle = useCallback((answer) => {
        setDialog((prev) => ({ ...prev, open: false }));
        resolver.current?.(answer);
        resolver.current = null;
    }, []);

    const confirm = useCallback(({ title, message, confirmLabel = 'Confirm', danger = false }) =>
        new Promise((resolve) => {
            resolver.current = resolve;
            setDialog({ open: true, title, message, confirmLabel, danger });
        }), []);

    const value = useMemo(() => ({ confirm }), [confirm]);

    return (
        <DialogContext.Provider value={value}>
            {children}
            <Modal
                open={dialog.open}
                onClose={() => settle(false)}
                title={dialog.title}
                description={dialog.message}
                size="sm"
                footer={
                    <>
                        <Button variant="ghost" onClick={() => settle(false)}>Cancel</Button>
                        <Button
                            variant={dialog.danger ? 'danger' : 'primary'}
                            onClick={() => settle(true)}
                        >
                            {dialog.confirmLabel}
                        </Button>
                    </>
                }
            />
        </DialogContext.Provider>
    );
}
