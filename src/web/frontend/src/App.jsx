import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import BootPage from './pages/BootPage';
import HomePage from './pages/HomePage';
import ChatPage from './pages/ChatPage';
import PlanPage from './pages/PlanPage';
import ActivityPage from './pages/ActivityPage';
import MemoryPage from './pages/MemoryPage';
import SkillsPage from './pages/SkillsPage';
import SettingsPage from './pages/SettingsPage';
import OnboardingPage from './pages/OnboardingPage';

export default function App() {
    return (
        <Routes>
            <Route path="/" element={<BootPage />} />
            <Route path="/dashboard" element={<AppShell />}>
                <Route index element={<HomePage />} />
                <Route path="chat" element={<ChatPage />} />
                <Route path="plan" element={<PlanPage />} />
                <Route path="activity" element={<ActivityPage />} />
                <Route path="memory" element={<MemoryPage />} />
                <Route path="skills" element={<SkillsPage />} />
                <Route path="onboarding" element={<OnboardingPage />} />
                <Route path="settings" element={<Navigate to="/dashboard/settings/mind" replace />} />
                <Route path="settings/:section" element={<SettingsPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
    );
}
