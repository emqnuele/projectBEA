import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const STORAGE_KEY = 'bea.appearance';

export const DEFAULTS = {
    theme: 'dark',          // dark | light
    accent: '#3d7dff',      // the one hue the interface is allowed
    glass: true,            // refraction on or off entirely
    frost: 18,              // blur behind the surface, px
    light: 0.5,             // specular highlight strength
    depth: 1,               // how far the surface floats off the page
    splay: 0.62,            // how far in from the rim the warp reaches
    refraction: 42,         // displacement scale — the water-droplet bend
    dispersion: 26,         // RGB split at the edge, the rainbow fringe
    saturate: 1.5,          // colour lift of whatever is behind
    dither: true,           // the atmospheric backdrop
};

const AppearanceContext = createContext(null);

export function useAppearance() {
    const value = useContext(AppearanceContext);
    if (!value) throw new Error('useAppearance must be used inside <AppearanceProvider>');
    return value;
}

function load() {
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        return { ...DEFAULTS, ...saved };
    } catch {
        return { ...DEFAULTS };
    }
}

export function AppearanceProvider({ children }) {
    const [settings, setSettings] = useState(load);

    useEffect(() => {
        const root = document.documentElement;
        root.dataset.theme = settings.theme;
        root.dataset.glass = settings.glass ? 'on' : 'off';
        root.style.setProperty('--accent-raw', settings.accent);
        root.style.setProperty('--lg-frost', `${settings.frost}px`);
        root.style.setProperty('--lg-light', String(settings.light));
        root.style.setProperty('--lg-depth', String(settings.depth));
        root.style.setProperty('--lg-splay', String(settings.splay));
        root.style.setProperty('--lg-saturate', String(settings.saturate));
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
        } catch { /* private mode: the session still works, it just won't persist */ }
    }, [settings]);

    const set = useCallback((key, value) => setSettings((prev) => ({ ...prev, [key]: value })), []);
    const reset = useCallback(() => setSettings({ ...DEFAULTS }), []);
    const toggleTheme = useCallback(
        () => setSettings((prev) => ({ ...prev, theme: prev.theme === 'dark' ? 'light' : 'dark' })),
        [],
    );

    const value = useMemo(
        () => ({ settings, set, reset, toggleTheme }),
        [settings, set, reset, toggleTheme],
    );

    return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}
