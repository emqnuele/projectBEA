import React from 'react';
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { WifiOff } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { CommandPalette } from './components/CommandPalette';
import { useStore } from './store';
import { useEventStream, useStatusPolling } from './hooks/useStreaming';

// --- page imports ---
import OverviewPage from './pages/OverviewPage';
import WorkspacePage from './pages/WorkspacePage';
import MemoryPage from './pages/MemoryPage';
import DreamStudioPage from './pages/DreamStudioPage';
import AgentsPage from './pages/AgentsPage';
import SkillsPage from './pages/SkillsPage';
import MCPPage from './pages/MCPPage';
import ArtifactsPage from './pages/ArtifactsPage';
import ActivityPage from './pages/ActivityPage';
import SystemPage from './pages/SystemPage';

export default function App() {
    return (
        <Routes>
            <Route path="/" element={<CommandCenter />}>
                <Route index element={<OverviewPage />} />
                <Route path="overview" element={<OverviewPage />} />
                <Route path="workspace" element={<WorkspacePage />} />
                <Route path="memory" element={<MemoryPage />} />
                <Route path="dream-studio" element={<DreamStudioPage />} />
                <Route path="agents" element={<AgentsPage />} />
                <Route path="skills" element={<SkillsPage />} />
                <Route path="mcp" element={<MCPPage />} />
                <Route path="artifacts" element={<ArtifactsPage />} />
                <Route path="activity" element={<ActivityPage />} />
                <Route path="system" element={<SystemPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
    );
}

function CommandCenter() {
    useEventStream();
    useStatusPolling();

    const [paletteOpen, setPaletteOpen] = React.useState(false);
    const connection = useStore((s) => s.connection);

    React.useEffect(() => {
        const onKeyDown = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                setPaletteOpen((open) => !open);
            }
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, []);

    return (
        <div className="flex h-full w-full gap-2.5 p-2.5 sm:gap-3 sm:p-3">
            <Sidebar />

            <div className="flex min-w-0 flex-1 flex-col gap-2.5 sm:gap-3">
                <TopBar onOpenPalette={() => setPaletteOpen(true)} />

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
                            <span>The brain stopped answering. Start it with <code className="font-mono">uv run shura --web</code> and this clears itself.</span>
                        </motion.div>
                    )}
                </AnimatePresence>

                <main className="relative min-h-0 flex-1">
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={window.location.pathname}
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
