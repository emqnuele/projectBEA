import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
    ChevronLeft, Menu, PanelLeft, Settings, X,
} from 'lucide-react';
import { SURFACES } from '../lib/nav';
import { useStore } from '../store';
import { cn } from '../lib/cn';
import { Glass } from './glass/Glass';
import { IconButton } from './ui/controls';

export function Sidebar() {
    const [menuOpen, setMenuOpen] = useState(false);
    const { sidebarCollapsed, toggleSidebar, activeSurface, setActiveSurface } = useStore();
    const location = useLocation();
    const collapsed = sidebarCollapsed;

    // Derive active surface from current path
    const currentSurface = SURFACES.find((s) => location.pathname.startsWith(s.to))?.to || '/overview';

    return (
        <>
            <AnimatePresence>
                {menuOpen && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        onClick={() => setMenuOpen(false)}
                        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] lg:hidden"
                    />
                )}
            </AnimatePresence>

            <Glass
                as="nav"
                aria-label="Navigation"
                className={cn(
                    'fixed inset-y-0 left-0 z-50 flex w-[264px] flex-col overflow-hidden rounded-none border-y-0 border-l-0 p-3',
                    'transition-transform duration-300 lg:static lg:z-auto lg:h-full lg:rounded-b4 lg:border',
                    'lg:translate-x-0 lg:transition-[width] lg:duration-300',
                    collapsed ? 'lg:w-[72px]' : 'lg:w-[248px]',
                    menuOpen ? 'translate-x-0' : '-translate-x-full',
                )}
            >
                {/* --- brand --- */}
                <header className={cn('mb-4 flex shrink-0 items-center', collapsed ? 'justify-center' : 'gap-2.5 px-1')}>
                    <BrandMark />
                    {!collapsed && (
                        <IconButton
                            label="Collapse sidebar"
                            size="sm"
                            onClick={toggleSidebar}
                            className="ml-auto max-lg:hidden"
                        >
                            <ChevronLeft size={14} />
                        </IconButton>
                    )}
                    <IconButton label="Close menu" size="sm" onClick={() => setMenuOpen(false)} className="ml-auto lg:hidden">
                        <X size={15} />
                    </IconButton>
                </header>

                {/* --- surfaces --- */}
                <ul className="shrink-0 space-y-0.5">
                    {SURFACES.map((surface) => {
                        const isActive = currentSurface === surface.to;
                        return (
                            <li key={surface.to}>
                                <NavLink
                                    to={surface.to}
                                    end={surface.end}
                                    onClick={() => setMenuOpen(false)}
                                    title={collapsed ? surface.label : undefined}
                                    className={cn(
                                        'group relative flex items-center rounded-b2 py-2 text-[13px] font-medium transition-colors',
                                        collapsed ? 'justify-center px-0' : 'gap-3 px-2.5',
                                        isActive ? 'text-text' : 'text-dim hover:bg-fill-2 hover:text-text',
                                    )}
                                >
                                    {isActive && (
                                        <motion.span
                                            layoutId="nav-active"
                                            transition={{ type: 'spring', stiffness: 520, damping: 40 }}
                                            className="absolute inset-0 rounded-b2 border border-line bg-fill-3"
                                        />
                                    )}
                                    <span className="relative shrink-0"><surface.icon size={17} /></span>
                                    {!collapsed && <span className="relative truncate">{surface.label}</span>}
                                    {!collapsed && (
                                        <span className="relative ml-auto font-mono text-[10px] text-faint">
                                            {surface.shortcut || ''}
                                        </span>
                                    )}
                                </NavLink>
                            </li>
                        );
                    })}
                </ul>

                <div className="mt-auto" />

                {/* --- bottom --- */}
                <div className="mt-2 shrink-0 border-t border-line pt-2">
                    {collapsed && (
                        <div className="mb-1 flex justify-center">
                            <IconButton label="Expand sidebar" onClick={toggleSidebar}>
                                <PanelLeft size={17} />
                            </IconButton>
                        </div>
                    )}
                    <NavLink
                        to="/system"
                        title={collapsed ? 'System' : undefined}
                        className={cn(
                            'flex items-center rounded-b2 py-2 text-[13px] font-medium transition-colors',
                            collapsed ? 'justify-center px-0' : 'gap-3 px-2.5',
                            location.pathname.startsWith('/system') ? 'bg-fill-3 text-text' : 'text-dim hover:bg-fill-2 hover:text-text',
                        )}
                    >
                        <Settings size={17} className="shrink-0" />
                        {!collapsed && <span>System</span>}
                    </NavLink>
                    {!collapsed && (
                        <p className="truncate px-2.5 pt-2 font-mono text-[10px] tracking-wider text-faint">
                            SHURA // Command Center
                        </p>
                    )}
                </div>
            </Glass>
        </>
    );
}

function BrandMark() {
    const collapsed = useStore((s) => s.sidebarCollapsed);
    return (
        <div className={cn('flex min-w-0 items-center', collapsed ? 'justify-center' : 'gap-2.5')}>
            <div className="relative grid h-8 w-8 shrink-0 place-items-center rounded-b2 bg-accent/10 text-accent">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                    <path d="M2 17l10 5 10-5" />
                    <path d="M2 12l10 5 10-5" />
                </svg>
            </div>
            {!collapsed && (
                <span className="min-w-0">
                    <span className="block truncate font-display text-[13px] font-bold leading-none text-text">SHURA</span>
                    <span className="mt-1 block truncate text-[10px] uppercase tracking-widest text-faint">Command Center</span>
                </span>
            )}
        </div>
    );
}
