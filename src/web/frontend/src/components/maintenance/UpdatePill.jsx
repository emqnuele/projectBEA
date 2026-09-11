import React from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDownToLine, RotateCw, X } from 'lucide-react';
import { useUpdate } from '../../state/UpdateProvider';

/**
 * The one piece of update chrome that follows you around.
 *
 * It has two things to say and they are not the same thing: there is a new
 * version, or there is a new version already on disk and she is still running
 * the old one. The second matters more — somebody has already clicked, and
 * without this they would sit looking at the old dashboard wondering whether
 * the update did anything.
 */
export function UpdatePill() {
    const { available, running, restartRequired, status, dismiss } = useUpdate();
    const navigate = useNavigate();

    const mode = restartRequired ? 'restart' : running ? 'running' : available ? 'available' : null;
    if (!mode) return null;

    const copy = {
        available: { icon: ArrowDownToLine, label: `Update · ${status?.behind}`, colour: 'var(--vital)' },
        running: { icon: ArrowDownToLine, label: 'Updating…', colour: 'var(--flux-think)' },
        restart: { icon: RotateCw, label: 'Restart to finish', colour: 'var(--vital)' },
    }[mode];
    const Icon = copy.icon;

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0, scale: 0.94 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.94 }}
                transition={{ type: 'spring', stiffness: 520, damping: 34 }}
                className="flex items-center"
            >
                <button
                    onClick={() => navigate('/dashboard/maintenance')}
                    title="Open maintenance"
                    className="inline-flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold transition-all hover:brightness-110"
                    style={{
                        color: copy.colour,
                        borderColor: `color-mix(in srgb, ${copy.colour} 34%, transparent)`,
                        background: `color-mix(in srgb, ${copy.colour} 12%, transparent)`,
                    }}
                >
                    <motion.span
                        animate={mode === 'running' ? { y: [0, 2, 0] } : {}}
                        transition={{ repeat: Infinity, duration: 1.4, ease: 'easeInOut' }}
                        className="grid place-items-center"
                    >
                        <Icon size={12} strokeWidth={2.6} />
                    </motion.span>
                    <span className="hidden sm:inline">{copy.label}</span>
                </button>

                {mode === 'available' && (
                    <button
                        onClick={() => dismiss(status?.latest)}
                        aria-label="Not now"
                        title="Not now"
                        className="-ml-1 grid h-8 w-6 place-items-center rounded-full text-faint transition-colors hover:text-text"
                    >
                        <X size={11} />
                    </button>
                )}
            </motion.div>
        </AnimatePresence>
    );
}
