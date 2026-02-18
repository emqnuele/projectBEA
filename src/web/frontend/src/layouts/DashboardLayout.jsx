import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar from '../components/Sidebar';
import ChatPage from '../pages/ChatPage';
import ConfigPage from '../pages/ConfigPage';
import SkillsPage from '../pages/SkillsPage';
import BrainActivityPage from '../pages/BrainActivityPage';

const DashboardLayout = () => {
    const [view, setView] = useState('chat'); // 'chat', 'config', 'skills', 'activity'
    const [configCategory, setConfigCategory] = useState('LLM'); // default config tab
    const [chatKey, setChatKey] = useState(0);

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="flex h-screen w-full bg-white text-zinc-900 overflow-hidden"
        >
            <Sidebar
                view={view}
                setView={setView}
                configCategory={configCategory}
                setConfigCategory={setConfigCategory}
                onSessionChange={() => setChatKey(prev => prev + 1)}
            />
            <main className="flex-1 h-full overflow-hidden bg-white relative">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={view === 'config' ? `config-${configCategory}` : view}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.2, ease: "easeOut" }}
                        className="h-full w-full"
                    >
                        {view === 'chat' && <ChatPage key={chatKey} />}
                        {view === 'activity' && <BrainActivityPage />}
                        {view === 'config' && <ConfigPage activeCategory={configCategory} />}
                        {view === 'skills' && <SkillsPage />}
                    </motion.div>
                </AnimatePresence>
            </main>
        </motion.div>
    );
};

export default DashboardLayout;
