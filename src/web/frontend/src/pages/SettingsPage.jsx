import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { RotateCcw, Save } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { SETTINGS_SECTIONS } from '../lib/nav';
import { useToast } from '../state/ToastProvider';
import { useBrain } from '../state/BrainProvider';
import { Glass } from '../components/glass/Glass';
import { Button } from '../components/ui/controls';
import { Skeleton } from '../components/ui/feedback';
import { SECTIONS } from './settings/sections';
import { AppearanceSection } from './settings/AppearanceSection';

/**
 * One page, one config object, one save.
 *
 * The old version remounted itself on every category change and silently threw
 * away whatever you had typed. Sections are routes now, but the state lives
 * above them, so moving between sections keeps your edits and the save bar
 * follows you until you commit them.
 */
export default function SettingsPage() {
    const { section = 'mind' } = useParams();
    const [config, setConfig] = useState(null);
    const [saved, setSaved] = useState(null);
    const [secrets, setSecrets] = useState({});
    const [devices, setDevices] = useState([]);
    const [saving, setSaving] = useState(false);

    const toast = useToast();
    const { refreshOverview } = useBrain();
    const loadedOnce = useRef(false);

    const load = useCallback(async () => {
        try {
            const data = await api.config();
            setConfig(data);
            setSaved(JSON.stringify(data));
        } catch (e) {
            toast.error('Could not read the settings', e.message);
            setConfig({});
            setSaved('{}');
        }
        api.secrets?.().then(setSecrets).catch(() => { });
        api.audioDevices().then(setDevices).catch(() => setDevices([]));
    }, [toast]);

    useEffect(() => {
        if (loadedOnce.current) return;
        loadedOnce.current = true;
        load();
    }, [load]);

    const dirty = useMemo(
        () => Boolean(config && saved && JSON.stringify(config) !== saved),
        [config, saved],
    );

    // leaving the tab with unsaved edits should cost a confirmation, not the edits
    useEffect(() => {
        if (!dirty) return undefined;
        const warn = (event) => { event.preventDefault(); event.returnValue = ''; };
        window.addEventListener('beforeunload', warn);
        return () => window.removeEventListener('beforeunload', warn);
    }, [dirty]);

    const update = useCallback((key, value) => {
        setConfig((prev) => ({ ...prev, [key]: value }));
    }, []);

    const updateSkill = useCallback((skill, key, value) => {
        setConfig((prev) => ({
            ...prev,
            skills: { ...prev.skills, [skill]: { ...prev.skills?.[skill], [key]: value } },
        }));
    }, []);

    const save = async () => {
        setSaving(true);
        try {
            const result = await api.saveConfig(config);
            setSaved(JSON.stringify(config));
            if (result.restart_required) {
                toast.info('Saved — restart to apply', 'Switching provider needs the engine restarted.');
            } else {
                toast.success('Settings saved', 'She is already using them.');
            }
            await refreshOverview();
        } catch (e) {
            toast.error('Nothing was saved', e.message);
        } finally {
            setSaving(false);
        }
    };

    const discard = () => {
        setConfig(JSON.parse(saved));
        toast.info('Changes discarded');
    };

    const current = SETTINGS_SECTIONS.find((s) => s.id === section) || SETTINGS_SECTIONS[0];
    const Section = section === 'appearance' ? AppearanceSection : SECTIONS[section];

    return (
        <div className="flex h-full min-h-0 gap-2.5">
            <Glass quiet className="hidden w-56 shrink-0 flex-col overflow-y-auto rounded-b3 p-2 lg:flex">
                {SETTINGS_SECTIONS.map((item) => (
                    <NavLink
                        key={item.id}
                        to={`/dashboard/settings/${item.id}`}
                        className={({ isActive }) => cn(
                            'rounded-b2 px-3 py-2 transition-colors',
                            isActive ? 'bg-white/[0.08] text-text' : 'text-dim hover:bg-white/5 hover:text-text',
                        )}
                    >
                        <span className="block text-[13px] font-medium">{item.label}</span>
                        <span className="mt-0.5 block text-[11px] leading-snug text-faint">{item.hint}</span>
                    </NavLink>
                ))}
            </Glass>

            <div className="flex min-w-0 flex-1 flex-col gap-2.5">
                <Glass quiet className="shrink-0 rounded-b3 px-4 py-3 lg:hidden">
                    <div className="flex gap-1.5 overflow-x-auto pb-1">
                        {SETTINGS_SECTIONS.map((item) => (
                            <NavLink
                                key={item.id}
                                to={`/dashboard/settings/${item.id}`}
                                className={({ isActive }) => cn(
                                    'shrink-0 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                                    isActive ? 'border-line-strong bg-white/[0.08] text-text' : 'border-line text-dim',
                                )}
                            >
                                {item.label}
                            </NavLink>
                        ))}
                    </div>
                </Glass>

                <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
                    <div className="mx-auto w-full max-w-2xl pb-24">
                        <header className="mb-5">
                            <h1 className="font-display text-2xl font-bold tracking-tight text-text">{current.label}</h1>
                            <p className="mt-1 text-[13px] text-dim">{current.hint}</p>
                        </header>

                        {config === null ? (
                            <div className="space-y-3">
                                <Skeleton className="h-24" />
                                <Skeleton className="h-40" />
                                <Skeleton className="h-32" />
                            </div>
                        ) : Section ? (
                            <Section
                                config={config}
                                update={update}
                                updateSkill={updateSkill}
                                secrets={secrets}
                                devices={devices}
                                setConfig={setConfig}
                            />
                        ) : (
                            <p className="text-[13px] text-faint">That section does not exist.</p>
                        )}
                    </div>
                </div>
            </div>

            <AnimatePresence>
                {dirty && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 20 }}
                        transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                        className="pointer-events-none fixed inset-x-0 bottom-4 z-40 flex justify-center px-4"
                    >
                        <Glass className="pointer-events-auto flex items-center gap-3 rounded-full py-2 pl-5 pr-2">
                            <span className="text-[13px] text-dim">Unsaved changes</span>
                            <Button variant="ghost" size="sm" onClick={discard}>
                                <RotateCcw size={13} /> Discard
                            </Button>
                            <Button variant="primary" size="sm" onClick={save} loading={saving}>
                                <Save size={13} /> Save
                            </Button>
                        </Glass>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
