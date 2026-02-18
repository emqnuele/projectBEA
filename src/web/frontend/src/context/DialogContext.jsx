import React, { createContext, useContext, useState, useCallback } from 'react';
import CustomDialog from '../components/ui/CustomDialog';

const DialogContext = createContext();

export function useDialog() {
    return useContext(DialogContext);
}

export function DialogProvider({ children }) {
    const [dialogState, setDialogState] = useState({
        isOpen: false,
        title: '',
        message: '',
        onConfirm: () => { },
        onCancel: () => { },
        type: 'confirm'
    });

    const openConfirm = useCallback((message, title = 'Confirm') => {
        return new Promise((resolve) => {
            setDialogState({
                isOpen: true,
                title,
                message,
                type: 'confirm',
                onConfirm: () => {
                    setDialogState(prev => ({ ...prev, isOpen: false }));
                    resolve(true);
                },
                onCancel: () => {
                    setDialogState(prev => ({ ...prev, isOpen: false }));
                    resolve(false);
                }
            });
        });
    }, []);

    const openAlert = useCallback((message, title = 'Alert') => {
        return new Promise((resolve) => {
            setDialogState({
                isOpen: true,
                title,
                message,
                type: 'alert',
                onConfirm: () => {
                    setDialogState(prev => ({ ...prev, isOpen: false }));
                    resolve(true);
                },
                onCancel: () => {
                    setDialogState(prev => ({ ...prev, isOpen: false }));
                    resolve(true);
                }
            });
        });
    }, []);


    return (
        <DialogContext.Provider value={{ confirm: openConfirm, alert: openAlert }}>
            {children}
            <CustomDialog
                isOpen={dialogState.isOpen}
                title={dialogState.title}
                message={dialogState.message}
                onConfirm={dialogState.onConfirm}
                onCancel={dialogState.onCancel}
                type={dialogState.type}
            />
        </DialogContext.Provider>
    );
}
