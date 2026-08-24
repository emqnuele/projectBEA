import React, { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { WifiOff } from 'lucide-react';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { CommandPalette } from '../components/CommandPalette';
import { useBrain } from '../state/BrainProvider';

export default function AppShell() {
    const [menuOpen, setMenuOpen] = useState(false);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const location = useLocation();
    const { connection } = useBrain();

    // the page transition is keyed by the section, not the full path: moving
    // between settings sections must not tear down and refetch the page
    const sectionKey = location.pathname.split('/')[2] || 'overview';

    useEffect(() => {
        const onKeyDown = (event) => {
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                setPaletteOpen((open) => !open);
            }
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, []);

    useEffect(() => { setMenuOpen(false); }, [location.pathname]);

    return (
        <div className="flex h-full w-full gap-2.5 p-2.5 sm:gap-3 sm:p-3">
            <Sidebar mobileOpen={menuOpen} onCloseMobile={() => setMenuOpen(false)} />

            <div className="flex min-w-0 flex-1 flex-col gap-2.5 sm:gap-3">
                <TopBar onOpenMenu={() => setMenuOpen(true)} onOpenPalette={() => setPaletteOpen(true)} />

                <AnimatePresence>
                    {connection === 'offline' && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            role="alert"
                            className="flex items-center gap-2.5 overflow-hidden rounded-b2 border px-3.5 py-2.5 text-[13px]"
                            style={{
                                color: 'var(--flux-err)',
                                borderColor: 'color-mix(in srgb, var(--flux-err) 34%, transparent)',
                                background: 'color-mix(in srgb, var(--flux-err) 10%, transparent)',
                            }}
                        >
                            <WifiOff size={15} className="shrink-0" />
                            <span>
                                The brain stopped answering. Everything on screen is the last thing it said —
                                start it with <code className="font-mono">uv run bea --web</code> and this clears itself.
                            </span>
                        </motion.div>
                    )}
                </AnimatePresence>

                <main className="relative min-h-0 flex-1">
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={sectionKey}
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -6 }}
                            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                            className="h-full"
                        >
                            <Outlet />
                        </motion.div>
                    </AnimatePresence>
                </main>
            </div>

            <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
        </div>
    );
}
