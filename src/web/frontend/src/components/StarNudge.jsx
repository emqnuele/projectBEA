import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Star } from 'lucide-react';
import { Glass } from './glass/Glass';
import { Button } from './ui/controls';

const REPO = 'https://github.com/emqnuele/projectBEA';

const KEY = {
    visits: 'bea.star.visits',
    lastShown: 'bea.star.shown',
    never: 'bea.star.never',
};

// asking somebody to vouch for software they have used twice is asking a
// stranger for a reference
const AFTER_VISITS = 6;

// if the answer was "not now", it stays "not now" for a fortnight
const QUIET_FOR = 14 * 24 * 60 * 60 * 1000;

function read(key, fallback = 0) {
    try {
        return Number(localStorage.getItem(key)) || fallback;
    } catch {
        return fallback;
    }
}

function store(key, value) {
    try {
        localStorage.setItem(key, String(value));
    } catch { /* private windows are allowed to have opinions */ }
}

/**
 * An occasional, dismissible ask for a GitHub star.
 *
 * The only way this feature fails is by being annoying, so all of the logic is
 * about not appearing: not before somebody has actually used her, not twice in
 * a fortnight, and never again once they have said so. It is also the only
 * thing on this screen that has nothing to do with running her, which is why it
 * sits at the bottom of the page rather than in the chrome.
 */
export function StarNudge() {
    const [show, setShow] = useState(false);

    useEffect(() => {
        if (read(KEY.never)) return;

        const visits = read(KEY.visits) + 1;
        store(KEY.visits, visits);
        if (visits < AFTER_VISITS) return;

        const lastShown = read(KEY.lastShown);
        if (lastShown && Date.now() - lastShown < QUIET_FOR) return;

        store(KEY.lastShown, Date.now());
        setShow(true);
    }, []);

    if (!show) return null;

    const close = (forever) => () => {
        if (forever) store(KEY.never, 1);
        setShow(false);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6, type: 'spring', stiffness: 380, damping: 34 }}
        >
            <Glass quiet className="mt-2.5 flex flex-wrap items-center justify-between gap-3 rounded-b3 p-4">
                <div className="flex min-w-0 items-center gap-3">
                    <span
                        className="grid h-9 w-9 shrink-0 place-items-center rounded-b2"
                        style={{ background: 'var(--vital-soft)', color: 'var(--vital)' }}
                    >
                        <Star size={16} />
                    </span>
                    <div className="min-w-0">
                        <h2 className="font-display text-[13px] font-semibold text-text">
                            Enjoying her? Star the repo
                        </h2>
                        <p className="mt-0.5 text-[11px] leading-snug text-faint">
                            It is free, it takes a second, and it is how other people find this.
                        </p>
                    </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                    <Button variant="ghost" size="sm" onClick={close(true)}>Don&apos;t ask again</Button>
                    {/* an anchor, not a button: the star happens on GitHub, and
                        this is the one control on the dashboard that leaves it */}
                    <a
                        href={REPO}
                        target="_blank"
                        rel="noreferrer noopener"
                        onClick={close(true)}
                        className="inline-flex h-8 select-none items-center gap-1.5 rounded-b1 border border-transparent
                                   bg-text px-3 text-xs font-semibold text-bg transition-all duration-150
                                   hover:opacity-90 active:scale-[0.98]"
                    >
                        <Star size={13} /> Star on GitHub
                    </a>
                </div>
            </Glass>
        </motion.div>
    );
}
