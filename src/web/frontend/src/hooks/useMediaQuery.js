import { useEffect, useState } from 'react';

/** Reads a media query and keeps following it. */
export function useMediaQuery(query) {
    const [matches, setMatches] = useState(
        () => typeof window !== 'undefined' && window.matchMedia(query).matches,
    );

    useEffect(() => {
        const list = window.matchMedia(query);
        const update = (event) => setMatches(event.matches);
        setMatches(list.matches);
        list.addEventListener('change', update);
        return () => list.removeEventListener('change', update);
    }, [query]);

    return matches;
}

/** The breakpoint the sidebar rail switches on — Tailwind's `lg`. */
export const DESKTOP = '(min-width: 1024px)';
