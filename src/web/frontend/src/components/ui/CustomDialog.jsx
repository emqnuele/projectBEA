import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';

export default function CustomDialog({ isOpen, title, message, onConfirm, onCancel, type = 'confirm' }) {
    const [visible, setVisible] = useState(false);
    const [animate, setAnimate] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setVisible(true);
            // Small delay to allow render before animating in
            setTimeout(() => setAnimate(true), 10);
        } else {
            setAnimate(false);
            const timer = setTimeout(() => setVisible(false), 300); // Wait for animation
            return () => clearTimeout(timer);
        }
    }, [isOpen]);

    if (!visible) return null;

    return (
        <div className={`fixed inset-0 z-50 flex items-center justify-center transition-all duration-300 ${animate ? 'backdrop-blur-sm bg-black/20' : 'backdrop-blur-none bg-black/0'}`}>
            <div
                className={`bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full mx-4 border border-zinc-100 transform transition-all duration-500 cubic-bezier(0.16, 1, 0.3, 1) ${animate ? 'scale-100 opacity-100 translate-y-0' : 'scale-95 opacity-0 translate-y-4'}`}
            >
                {/* Header */}
                <div className="mb-4">
                    <h3 className="text-lg font-semibold text-zinc-900 leading-none tracking-tight">
                        {title || 'Confirm'}
                    </h3>
                    {message && (
                        <p className="mt-2 text-sm text-zinc-500 leading-relaxed">
                            {message}
                        </p>
                    )}
                </div>

                {/* Footer Controls */}
                <div className="flex items-center justify-end gap-2 mt-6">
                    {type === 'confirm' && (
                        <button
                            onClick={onCancel}
                            className="px-4 py-2 text-sm font-medium text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded-lg transition-colors"
                        >
                            Cancel
                        </button>
                    )}
                    <button
                        onClick={onConfirm}
                        className="px-4 py-2 text-sm font-medium bg-black text-white hover:bg-zinc-800 rounded-lg transition-colors shadow-sm"
                    >
                        OK
                    </button>
                </div>
            </div>
        </div>
    );
}
