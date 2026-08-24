const UNITS = [
    [60, 'second', 1],
    [3600, 'minute', 60],
    [86400, 'hour', 3600],
    [604800, 'day', 86400],
    [2629800, 'week', 604800],
    [31557600, 'month', 2629800],
];

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });

/** Seconds-since-epoch (or an ISO string) as "2 hours ago". */
export function relativeTime(value) {
    const seconds = toSeconds(value);
    if (seconds === null) return '';
    const delta = (Date.now() - seconds * 1000) / 1000;
    if (delta < 45) return 'just now';
    for (const [limit, unit, divisor] of UNITS) {
        if (delta < limit) return rtf.format(-Math.round(delta / divisor), unit);
    }
    return rtf.format(-Math.round(delta / 31557600), 'year');
}

export function clockTime(value) {
    const seconds = toSeconds(value);
    if (seconds === null) return '--:--:--';
    return new Date(seconds * 1000).toLocaleTimeString([], {
        hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
}

export function dayAndTime(value) {
    const seconds = toSeconds(value);
    if (seconds === null) return '';
    return new Date(seconds * 1000).toLocaleString([], {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
    });
}

function toSeconds(value) {
    if (value === null || value === undefined || value === '') return null;
    if (typeof value === 'number') return value > 1e11 ? value / 1000 : value;
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed / 1000;
}

/** 12400 → "12.4k". Keeps HUD numbers the same width as they grow. */
export function compact(n) {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    if (Math.abs(n) < 1000) return String(Math.round(n));
    if (Math.abs(n) < 1e6) return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`;
    return `${(n / 1e6).toFixed(1)}M`;
}

export function duration(seconds) {
    if (!seconds || seconds < 0) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m`;
    return `${Math.floor(seconds)}s`;
}

export function titleCase(value = '') {
    return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
