import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Flame, Heart, Save, Search, Sparkles, User, Users } from 'lucide-react';
import { api } from '../api';
import { compact, dayAndTime, relativeTime, titleCase } from '../lib/format';
import { useToast } from '../state/ToastProvider';
import { Glass } from '../components/glass/Glass';
import { Button, Segmented } from '../components/ui/controls';
import { Badge, EmptyState, Skeleton, Spinner } from '../components/ui/feedback';

const TABS = [
    { value: 'people', label: 'People she knows' },
    { value: 'roster', label: 'Everyone she has met' },
    { value: 'recall', label: 'Recall' },
    { value: 'self', label: 'Herself' },
];

/**
 * What she remembers, finally visible.
 *
 * The engine keeps person cards, a roster, a searchable memory and a self-lore
 * it writes on its own while she dreams. None of it had a screen: the only way
 * to see any of it was to open the SQLite file.
 */
export default function MemoryPage() {
    const [tab, setTab] = useState('people');
    const [people, setPeople] = useState(null);
    const [roster, setRoster] = useState(null);
    const [self, setSelf] = useState(null);
    const [saving, setSaving] = useState(false);
    const toast = useToast();

    const load = useCallback(async () => {
        const [p, r, s] = await Promise.allSettled([api.people(), api.roster(120), api.selfLore()]);
        setPeople(p.status === 'fulfilled' ? p.value : []);
        setRoster(r.status === 'fulfilled' ? r.value : []);
        setSelf(s.status === 'fulfilled' ? s.value : { facts: [], profile: {}, hot_facts: [] });
        if (p.status === 'rejected') toast.error('Could not read her memory', p.reason?.message);
    }, [toast]);

    useEffect(() => { load(); }, [load]);

    const saveNow = async () => {
        setSaving(true);
        try {
            const result = await api.saveMemory();
            if (result.status === 'success') {
                toast.success('This conversation went into long-term memory');
                await load();
            } else {
                toast.error('Nothing was saved', result.message);
            }
        } catch (e) {
            toast.error('Nothing was saved', e.message);
        } finally {
            setSaving(false);
        }
    };

    const loading = people === null;

    return (
        <div className="flex h-full flex-col gap-2.5">
            <Glass quiet className="flex flex-wrap items-center gap-3 rounded-b3 px-4 py-3">
                <div className="mr-auto flex items-center gap-2.5">
                    <Users size={15} className="text-faint" />
                    <div>
                        <h1 className="font-display text-[13px] font-semibold text-text">Memory</h1>
                        <p className="text-[11px] text-faint">
                            {loading ? 'reading…' : `${people.length} cards · ${roster.length} identities seen`}
                        </p>
                    </div>
                </div>
                <Segmented value={tab} onChange={setTab} options={TABS} size="sm" />
                <Button size="sm" variant="outline" onClick={saveNow} loading={saving}>
                    <Save size={13} /> Save this chat now
                </Button>
            </Glass>

            <div className="min-h-0 flex-1 overflow-y-auto pr-0.5">
                {loading ? (
                    <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                        {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-40" />)}
                    </div>
                ) : tab === 'people' ? (
                    <PeopleGrid people={people} />
                ) : tab === 'roster' ? (
                    <RosterTable roster={roster} />
                ) : tab === 'recall' ? (
                    <RecallPanel />
                ) : (
                    <SelfPanel self={self} />
                )}
            </div>
        </div>
    );
}

function PeopleGrid({ people }) {
    if (people.length === 0) {
        return (
            <EmptyState icon={User} title="She has not written anyone down yet">
                A card appears once someone has been around long enough to be worth remembering —
                the dream pass is what writes them.
            </EmptyState>
        );
    }

    return (
        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
            {people.map((person, index) => (
                <motion.div
                    key={person.person_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(index * 0.03, 0.3) }}
                >
                    <Glass quiet className="flex h-full flex-col rounded-b3 p-4">
                        <div className="flex items-start gap-3">
                            <span
                                className="grid h-9 w-9 shrink-0 place-items-center rounded-b2 font-display text-sm font-bold"
                                style={{ background: 'var(--cognition-soft)', color: 'var(--cognition)' }}
                            >
                                {person.name.slice(0, 1).toUpperCase()}
                            </span>
                            <div className="min-w-0 flex-1">
                                <p className="truncate font-display text-sm font-semibold text-text">{person.name}</p>
                                <p className="truncate font-mono text-[10px] text-faint">
                                    {person.identities.map((id) => id.split(':')[0]).filter((v, i, a) => a.indexOf(v) === i).join(' · ') || 'unknown'}
                                </p>
                            </div>
                        </div>

                        {person.attitude && (
                            <p
                                className="mt-3 flex items-start gap-2 rounded-b2 px-2.5 py-2 text-[12px] italic leading-snug"
                                style={{ background: 'var(--vital-soft)', color: 'var(--text)' }}
                            >
                                <Heart size={12} className="mt-0.5 shrink-0" style={{ color: 'var(--vital)' }} />
                                {person.attitude}
                            </p>
                        )}

                        {person.facts.length > 0 && (
                            <ul className="mt-3 space-y-1.5">
                                {person.facts.slice(-5).map((fact, i) => (
                                    <li key={i} className="flex gap-2 text-[12px] leading-snug text-dim">
                                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[color:var(--text-faint)]" />
                                        {fact}
                                    </li>
                                ))}
                            </ul>
                        )}

                        <p className="mt-auto pt-3 font-mono text-[10px] text-faint">
                            updated {relativeTime(person.last_updated)}
                            {person.facts.length > 5 && ` · ${person.facts.length} facts`}
                        </p>
                    </Glass>
                </motion.div>
            ))}
        </div>
    );
}

function RosterTable({ roster }) {
    const [query, setQuery] = useState('');

    const rows = useMemo(() => {
        const needle = query.trim().toLowerCase();
        if (!needle) return roster;
        return roster.filter((entry) =>
            entry.name?.toLowerCase().includes(needle) || entry.identity.toLowerCase().includes(needle));
    }, [roster, query]);

    if (roster.length === 0) {
        return (
            <EmptyState icon={Users} title="Nobody on the roster yet">
                Everyone who says something on any channel gets a tally here, long before she decides
                they are worth a card.
            </EmptyState>
        );
    }

    return (
        <Glass quiet className="overflow-hidden rounded-b3">
            <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
                <Search size={13} className="text-faint" />
                <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Find someone"
                    aria-label="Find someone on the roster"
                    className="w-full bg-transparent text-[12px] text-text outline-none placeholder:text-faint"
                />
                <span className="shrink-0 font-mono text-[10px] text-faint">{rows.length}</span>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full min-w-[36rem] text-left">
                    <thead>
                        <tr className="border-b border-line font-mono text-[9px] uppercase tracking-wider text-faint">
                            <th className="px-3 py-2 font-semibold">Name</th>
                            <th className="px-3 py-2 font-semibold">Where</th>
                            <th className="px-3 py-2 text-right font-semibold">Messages</th>
                            <th className="px-3 py-2 text-right font-semibold">Sessions</th>
                            <th className="px-3 py-2 text-right font-semibold">Last seen</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((entry) => (
                            <tr key={entry.identity} className="border-b border-line last:border-0 hover:bg-fill">
                                <td className="px-3 py-2">
                                    <span className="flex items-center gap-2">
                                        <span className="truncate text-[12px] text-text">{entry.name || entry.identity}</span>
                                        {entry.promoted && <Badge color="var(--cognition)">card</Badge>}
                                        {entry.marked && <Badge color="var(--vital)">noticed</Badge>}
                                    </span>
                                </td>
                                <td className="px-3 py-2 font-mono text-[11px] text-faint">{entry.platform}</td>
                                <td className="tnum px-3 py-2 text-right font-mono text-[11px] text-dim">{compact(entry.message_count)}</td>
                                <td className="tnum px-3 py-2 text-right font-mono text-[11px] text-dim">{entry.session_count}</td>
                                <td className="px-3 py-2 text-right font-mono text-[11px] text-faint">{relativeTime(entry.last_seen)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Glass>
    );
}

function RecallPanel() {
    const [query, setQuery] = useState('');
    const [result, setResult] = useState(null);
    const [busy, setBusy] = useState(false);
    const toast = useToast();

    const search = async (event) => {
        event?.preventDefault();
        const text = query.trim();
        if (!text) return;
        setBusy(true);
        try {
            setResult(await api.recall(text, 10));
        } catch (e) {
            toast.error('Recall failed', e.message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="mx-auto w-full max-w-3xl space-y-2.5">
            <Glass className="rounded-b3 p-5">
                <h2 className="font-display text-lg font-bold text-text">Ask her memory something</h2>
                <p className="mt-1 text-[12px] leading-relaxed text-dim">
                    The same semantic search she runs on herself every turn. Facts people told her are kept
                    apart from things she said herself — she invents on purpose, and her own lines must never
                    come back as truth.
                </p>
                <form onSubmit={search} className="mt-4 flex gap-2">
                    <input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="what does she know about minecraft?"
                        aria-label="Search her memory"
                        className="min-w-0 flex-1 rounded-b2 border border-line bg-fill px-3 py-2
                                   text-[13px] text-text outline-none transition-colors
                                   placeholder:text-faint focus:border-line-strong"
                    />
                    <Button type="submit" variant="primary" loading={busy} disabled={!query.trim()}>
                        <Search size={14} /> Recall
                    </Button>
                </form>
            </Glass>

            {busy && <div className="flex justify-center py-8"><Spinner size={20} /></div>}

            {result && !busy && (
                <div className="grid gap-2.5 md:grid-cols-2">
                    <RecallColumn
                        title="What people told her"
                        tone="var(--flux-in)"
                        items={result.facts}
                        empty="Nothing close enough in what others have said."
                    />
                    <RecallColumn
                        title="Things she said herself"
                        tone="var(--vital)"
                        items={result.hers}
                        empty="She has not said anything close to this."
                    />
                </div>
            )}
        </div>
    );
}

function RecallColumn({ title, tone, items, empty }) {
    return (
        <Glass quiet className="rounded-b3 p-4">
            <h3 className="mb-3 font-display text-[12px] font-semibold" style={{ color: tone }}>{title}</h3>
            {items.length === 0 ? (
                <p className="py-4 text-center text-[12px] text-faint">{empty}</p>
            ) : (
                <ul className="space-y-2">
                    {items.map((item, index) => (
                        <li key={index} className="rounded-b2 border border-line bg-fill p-2.5">
                            <p className="text-[12px] leading-snug text-text">{item.text}</p>
                            <p className="mt-1.5 flex items-center gap-2 font-mono text-[10px] text-faint">
                                {item.who && <span>{item.who}</span>}
                                <span>{dayAndTime(item.created_at)}</span>
                                <span className="ml-auto">{Math.round(item.similarity * 100)}% match</span>
                            </p>
                        </li>
                    ))}
                </ul>
            )}
        </Glass>
    );
}

function SelfPanel({ self }) {
    const profile = Object.entries(self.profile || {});

    return (
        <div className="mx-auto grid w-full max-w-4xl gap-2.5 lg:grid-cols-2">
            <Glass quiet className="rounded-b3 p-4">
                <h2 className="mb-1 flex items-center gap-2 font-display text-[13px] font-semibold text-text">
                    <Sparkles size={14} style={{ color: 'var(--cognition)' }} />
                    What she has worked out about herself
                </h2>
                <p className="mb-3 text-[11px] leading-snug text-faint">
                    Written by the dream pass. Her soul file never moves; this does.
                </p>
                {self.facts.length === 0 ? (
                    <p className="py-6 text-center text-[12px] text-faint">Nothing yet — she has not dreamt.</p>
                ) : (
                    <ul className="space-y-1.5">
                        {self.facts.map((fact, index) => (
                            <li key={index} className="flex gap-2.5 text-[12px] leading-snug text-dim">
                                <span className="tnum shrink-0 font-mono text-[10px] text-faint">
                                    {String(index + 1).padStart(2, '0')}
                                </span>
                                {fact}
                            </li>
                        ))}
                    </ul>
                )}
            </Glass>

            <div className="space-y-2.5">
                <Glass quiet className="rounded-b3 p-4">
                    <h2 className="mb-3 flex items-center gap-2 font-display text-[13px] font-semibold text-text">
                        <Flame size={14} style={{ color: 'var(--vital)' }} />
                        True right now
                    </h2>
                    {self.hot_facts.length === 0 ? (
                        <p className="py-4 text-center text-[12px] text-faint">
                            Nothing volatile in her head at the moment.
                        </p>
                    ) : (
                        <ul className="space-y-2">
                            {self.hot_facts.map((fact, index) => (
                                <li key={index} className="rounded-b2 border border-line bg-fill px-2.5 py-2">
                                    <p className="text-[12px] leading-snug text-text">{fact.text}</p>
                                    <p className="mt-1 font-mono text-[10px] text-faint">
                                        from {fact.source} · fades {relativeTime(fact.expires_at)}
                                    </p>
                                </li>
                            ))}
                        </ul>
                    )}
                </Glass>

                {profile.length > 0 && (
                    <Glass quiet className="rounded-b3 p-4">
                        <h2 className="mb-3 font-display text-[13px] font-semibold text-text">Her profile</h2>
                        <dl className="space-y-2">
                            {profile.map(([key, value]) => (
                                <div key={key} className="flex gap-3 border-b border-line pb-2 last:border-0 last:pb-0">
                                    <dt className="w-28 shrink-0 text-[11px] text-faint">{titleCase(key)}</dt>
                                    <dd className="min-w-0 flex-1 text-[12px] text-dim">{String(value)}</dd>
                                </div>
                            ))}
                        </dl>
                    </Glass>
                )}
            </div>
        </div>
    );
}
