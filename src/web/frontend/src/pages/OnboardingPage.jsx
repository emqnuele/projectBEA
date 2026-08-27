import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, ArrowRight, Check, RefreshCw, Sparkles } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/cn';
import { Glass } from '../components/glass/Glass';
import { Button } from '../components/ui/controls';
import { Field, Select, TextArea, TextInput } from '../components/ui/fields';
import { Skeleton } from '../components/ui/feedback';
import { useBrain } from '../state/BrainProvider';
import { useToast } from '../state/ToastProvider';

/**
 * Six questions and a character.
 *
 * The setup script covers the plumbing and never asks who she is, so almost
 * everyone runs the shipped persona forever. One question at a time, because a
 * form of seven boxes is a form people close.
 *
 * The draft is never saved on its own: you read it, edit it, and then it is
 * hers.
 */
export default function OnboardingPage() {
    const [questions, setQuestions] = useState(null);
    const [answers, setAnswers] = useState({});
    const [step, setStep] = useState(0);
    const [draft, setDraft] = useState(null);
    const [busy, setBusy] = useState(false);

    const navigate = useNavigate();
    const toast = useToast();
    const { refreshPersona } = useBrain();
    const field = useRef(null);

    useEffect(() => {
        api.onboarding()
            .then((data) => {
                setQuestions(data.questions);
                setAnswers(Object.fromEntries(
                    data.questions.map((q) => [q.key, q.default || '']),
                ));
            })
            .catch((e) => toast.error('Could not start the setup', e.message));
    }, [toast]);

    useEffect(() => { field.current?.focus(); }, [step, draft]);

    const current = questions?.[step];
    const last = questions ? step === questions.length - 1 : false;
    const blocked = Boolean(current?.required && !String(answers[current.key] || '').trim());

    const generate = useCallback(async () => {
        setBusy(true);
        try {
            const result = await api.draftPersona(answers);
            setDraft(result.soul);
        } catch (e) {
            toast.error('Could not write her', e.message);
        } finally {
            setBusy(false);
        }
    }, [answers, toast]);

    const commit = async () => {
        setBusy(true);
        try {
            await api.savePersona({ name: answers.name, soul: draft });
            await refreshPersona();
            toast.success(`${answers.name} is ready`, 'She is already being herself.');
            navigate('/dashboard/settings/personality');
        } catch (e) {
            toast.error('Nothing was saved', e.message);
        } finally {
            setBusy(false);
        }
    };

    const skip = async () => {
        try {
            await api.skipOnboarding();
        } catch { /* skipping is not worth an error */ }
        navigate('/dashboard');
    };

    if (!questions) {
        return (
            <div className="mx-auto w-full max-w-xl space-y-3 pt-10">
                <Skeleton className="h-8 w-40" />
                <Skeleton className="h-32" />
            </div>
        );
    }

    return (
        <div className="mx-auto flex h-full w-full max-w-xl flex-col justify-center py-8">
            <header className="mb-6">
                <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-faint">
                    {draft ? 'Read her over' : `Question ${step + 1} of ${questions.length}`}
                </span>
                <h1 className="mt-2 font-display text-2xl font-bold tracking-tight text-text">
                    {draft ? `This is ${answers.name}` : 'Who is she?'}
                </h1>
                <p className="mt-1 text-[13px] text-dim">
                    {draft
                        ? 'Change anything you disagree with. Nothing is saved until you say so.'
                        : 'Six answers, and she stops being the character we ship.'}
                </p>
            </header>

            <div className="mb-4 flex gap-1" aria-hidden="true">
                {questions.map((q, i) => (
                    <span
                        key={q.key}
                        className={cn(
                            'h-0.5 flex-1 rounded-full transition-colors duration-300',
                            draft || i < step ? 'bg-text' : i === step ? 'bg-dim' : 'bg-line',
                        )}
                    />
                ))}
            </div>

            <AnimatePresence mode="wait">
                {draft ? (
                    <motion.div
                        key="draft"
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                    >
                        <Glass quiet className="rounded-b3 p-4 sm:p-5">
                            <TextArea
                                ref={field}
                                value={draft}
                                onChange={(e) => setDraft(e.target.value)}
                                rows={18}
                                spellCheck="false"
                                className="font-mono text-[12.5px] leading-relaxed"
                            />
                            <p className="mt-2 text-[11px] leading-snug text-faint">
                                <span className="font-mono">{'{name}'}</span> is where her name
                                goes — leaving it there means you can rename her later without
                                rewriting any of this.
                            </p>
                        </Glass>

                        <div className="mt-4 flex flex-wrap items-center gap-2">
                            <Button variant="ghost" size="sm" onClick={() => setDraft(null)}>
                                <ArrowLeft size={13} /> Back to the questions
                            </Button>
                            <Button variant="outline" size="sm" onClick={generate} loading={busy}>
                                <RefreshCw size={13} /> Write another
                            </Button>
                            <Button
                                variant="primary"
                                size="sm"
                                className="ml-auto"
                                onClick={commit}
                                loading={busy}
                            >
                                <Check size={13} /> This is her
                            </Button>
                        </div>
                    </motion.div>
                ) : (
                    <motion.div
                        key={current.key}
                        initial={{ opacity: 0, x: 12 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -12 }}
                        transition={{ duration: 0.18 }}
                    >
                        <Glass quiet className="rounded-b3 p-4 sm:p-5">
                            <Field label={current.label} help={current.help} htmlFor={current.key}>
                                {current.type === 'select' ? (
                                    <Select
                                        id={current.key}
                                        ref={field}
                                        value={answers[current.key] || ''}
                                        onChange={(e) => setAnswers((a) => ({ ...a, [current.key]: e.target.value }))}
                                    >
                                        {current.options.map((option) => (
                                            <option key={option} value={option}>{option}</option>
                                        ))}
                                    </Select>
                                ) : (
                                    <TextInput
                                        id={current.key}
                                        ref={field}
                                        value={answers[current.key] || ''}
                                        placeholder={current.placeholder}
                                        onChange={(e) => setAnswers((a) => ({ ...a, [current.key]: e.target.value }))}
                                        onKeyDown={(e) => {
                                            if (e.key !== 'Enter' || blocked) return;
                                            last ? generate() : setStep((s) => s + 1);
                                        }}
                                    />
                                )}
                            </Field>
                        </Glass>

                        <div className="mt-4 flex items-center gap-2">
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setStep((s) => s - 1)}
                                disabled={step === 0}
                            >
                                <ArrowLeft size={13} /> Back
                            </Button>
                            <Button variant="ghost" size="sm" onClick={skip}>
                                Skip for now
                            </Button>
                            {last ? (
                                <Button
                                    variant="primary"
                                    size="sm"
                                    className="ml-auto"
                                    onClick={generate}
                                    loading={busy}
                                    disabled={blocked}
                                >
                                    <Sparkles size={13} /> Write her
                                </Button>
                            ) : (
                                <Button
                                    variant="primary"
                                    size="sm"
                                    className="ml-auto"
                                    onClick={() => setStep((s) => s + 1)}
                                    disabled={blocked}
                                >
                                    Next <ArrowRight size={13} />
                                </Button>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
