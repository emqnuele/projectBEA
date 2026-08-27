import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { RotateCcw, Save, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api';
import { Glass } from '../../components/glass/Glass';
import { Button } from '../../components/ui/controls';
import { Field, TextArea, TextInput } from '../../components/ui/fields';
import { Skeleton } from '../../components/ui/feedback';
import { useBrain } from '../../state/BrainProvider';
import { useToast } from '../../state/ToastProvider';
import { Group } from './parts';

const PRONOUN_PRESETS = ['she/her', 'he/him', 'they/them/their', 'lei/lei'];

/**
 * Who she is.
 *
 * Two different things on one screen, on purpose. The name and the pronouns are
 * structured — six other parts of the engine read them, so they live in config.
 * The character itself is prose, and prose belongs in a file you can open,
 * diff and edit outside this box. Saving either one reaches her immediately.
 */
export function PersonalitySection() {
    const [loaded, setLoaded] = useState(null);
    const [draft, setDraft] = useState(null);
    const [saving, setSaving] = useState(false);
    const toast = useToast();
    const { refreshPersona } = useBrain();
    const navigate = useNavigate();
    const alive = useRef(true);

    const load = useCallback(async () => {
        try {
            const data = await api.persona();
            if (!alive.current) return;
            setLoaded(data);
            setDraft({
                name: data.name,
                pronouns: data.pronouns,
                soul: data.soul,
                trigger_words: (data.derived_triggers ? [] : data.trigger_words).join(', '),
            });
        } catch (e) {
            toast.error('Could not read her persona', e.message);
        }
    }, [toast]);

    useEffect(() => {
        alive.current = true;
        load();
        return () => { alive.current = false; };
    }, [load]);

    const dirty = useMemo(() => {
        if (!loaded || !draft) return false;
        return draft.name !== loaded.name
            || draft.pronouns !== loaded.pronouns
            || draft.soul !== loaded.soul
            || draft.trigger_words !== (loaded.derived_triggers ? '' : loaded.trigger_words.join(', '));
    }, [loaded, draft]);

    const set = (key, value) => setDraft((prev) => ({ ...prev, [key]: value }));

    const save = async () => {
        setSaving(true);
        try {
            await api.savePersona({
                name: draft.name,
                pronouns: draft.pronouns,
                soul: draft.soul,
                trigger_words: draft.trigger_words
                    .split(',').map((w) => w.trim()).filter(Boolean),
            });
            await load();
            await refreshPersona();
            toast.success('Saved', 'She is already being herself.');
        } catch (e) {
            toast.error('Nothing was saved', e.message);
        } finally {
            setSaving(false);
        }
    };

    if (!draft) {
        return (
            <div className="space-y-3">
                <Skeleton className="h-32" />
                <Skeleton className="h-72" />
            </div>
        );
    }

    // what the gate will listen for once this is saved
    const listening = draft.trigger_words.trim()
        ? draft.trigger_words.split(',').map((w) => w.trim()).filter(Boolean)
        : [draft.name.trim().toLowerCase(), draft.name.trim().toLowerCase().split(' ')[0]]
            .filter((w, i, all) => w && all.indexOf(w) === i);

    return (
        <>
            {!loaded?.customised && (
                <Glass quiet className="mb-2.5 flex flex-wrap items-center justify-between gap-3 rounded-b3 p-4 sm:p-5">
                    <div className="min-w-0">
                        <h2 className="font-display text-[13px] font-semibold text-text">
                            She is still the character we ship
                        </h2>
                        <p className="mt-1 text-[11px] leading-snug text-faint">
                            Answer six questions and she becomes someone of yours instead.
                        </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => navigate('/dashboard/onboarding')}>
                        <Sparkles size={13} /> Set her up
                    </Button>
                </Glass>
            )}

            <Group
                title="Name"
                description="Everything follows this: what she answers to, how her own messages are filed, the name in the corner of this dashboard."
            >
                <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Called" htmlFor="persona-name">
                        <TextInput
                            id="persona-name"
                            value={draft.name}
                            onChange={(e) => set('name', e.target.value)}
                            placeholder="Bea"
                        />
                    </Field>
                    <Field
                        label="Referred to as"
                        htmlFor="persona-pronouns"
                        help="Two or three forms, separated by slashes."
                    >
                        <TextInput
                            id="persona-pronouns"
                            list="pronoun-presets"
                            value={draft.pronouns}
                            onChange={(e) => set('pronouns', e.target.value)}
                            placeholder="she/her"
                        />
                        <datalist id="pronoun-presets">
                            {PRONOUN_PRESETS.map((p) => <option key={p} value={p} />)}
                        </datalist>
                    </Field>
                </div>

                <Field
                    label="Also answers to"
                    htmlFor="persona-triggers"
                    help="Saying one of these always reaches her, cooldown or not. Leave it empty and it follows her name."
                >
                    <TextInput
                        id="persona-triggers"
                        value={draft.trigger_words}
                        onChange={(e) => set('trigger_words', e.target.value)}
                        placeholder={listening.join(', ')}
                    />
                </Field>

                <p className="text-[11px] leading-snug text-faint">
                    Right now she comes running for{' '}
                    {listening.map((word, i) => (
                        <React.Fragment key={word}>
                            {i > 0 && ', '}
                            <span className="font-mono text-dim">{word}</span>
                        </React.Fragment>
                    ))}
                    .
                </p>
            </Group>

            <Group
                title="Character"
                description="Written in her second person — 'You are…'. Use {name} where her name goes, so renaming her later still works. This is a file on disk; editing it here or in an editor is the same thing."
            >
                <TextArea
                    value={draft.soul}
                    onChange={(e) => set('soul', e.target.value)}
                    rows={22}
                    spellCheck="false"
                    className="font-mono text-[12.5px] leading-relaxed"
                    placeholder="# SOUL — Who {name} Is"
                />
                <p className="tnum text-[11px] text-faint">
                    {draft.soul.length} characters · the previous version is kept next to it as
                    {' '}<span className="font-mono">soul.md.bak</span>
                </p>
            </Group>

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
                            <Button variant="ghost" size="sm" onClick={load}>
                                <RotateCcw size={13} /> Discard
                            </Button>
                            <Button variant="primary" size="sm" onClick={save} loading={saving}>
                                <Save size={13} /> Save
                            </Button>
                        </Glass>
                    </motion.div>
                )}
            </AnimatePresence>
        </>
    );
}
