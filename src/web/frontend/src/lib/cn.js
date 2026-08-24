/** Joins class names, dropping anything falsy. */
export function cn(...parts) {
    return parts.filter(Boolean).join(' ');
}

/** The colour and label every event category carries, wherever it is shown. */
export const FLUX = {
    input: { label: 'IN', color: 'var(--flux-in)', name: 'Perception' },
    thought: { label: 'THINK', color: 'var(--flux-think)', name: 'Thought' },
    output: { label: 'OUT', color: 'var(--flux-out)', name: 'Speech' },
    skill: { label: 'ACT', color: 'var(--flux-act)', name: 'Action' },
    error: { label: 'FAIL', color: 'var(--flux-err)', name: 'Error' },
    system: { label: 'SYS', color: 'var(--flux-mute)', name: 'System' },
};

export function fluxOf(event) {
    if (!event) return FLUX.system;
    if (event.source === 'cost') return { label: 'COST', color: 'var(--flux-cost)', name: 'Cost' };
    if (event.source === 'attention') {
        const reaction = event.metadata?.reaction;
        if (reaction === 'react') return { label: 'WAKE', color: 'var(--flux-out)', name: 'Woke her' };
        if (reaction === 'note') return { label: 'NOTE', color: 'var(--flux-in)', name: 'Noted' };
        return { label: 'DROP', color: 'var(--flux-mute)', name: 'Ignored' };
    }
    return FLUX[event.category] || FLUX.system;
}
