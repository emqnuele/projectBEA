/**
 * The speech bubble, typed here instead of over the wire.
 *
 * The OBS backend sends one request per character. This one receives the line
 * once and animates it locally, which is both cheaper and smoother: the typing
 * is driven by requestAnimationFrame rather than by network round trips.
 */

const DEFAULTS = {
    typing_delay: 0.03,
    text_line_width: 40,
    text_lines: 4,
    text_font_size: 75,
};

// the height the configured font size is measured against, the canvas an OBS text source is usually laid out on
export const REFERENCE_HEIGHT = 1080;

/**
 * The box a caption is drawn in, from the configured typography. Pure, so node can test it.
 *
 * The size scales with the frame, so a 1080p source and the dashboard's small
 * preview show the same proportions; the width wraps where the OBS caption
 * would, never wider than the frame; and only the last `text_lines` lines show.
 */
export function captionStyle(settings) {
    const lines = Math.max(1, Math.round(Number(settings.text_lines) || DEFAULTS.text_lines));
    return {
        '--caption-size': String(Number(settings.text_font_size) || DEFAULTS.text_font_size),
        '--caption-lines': String(lines),
        maxWidth: `min(90vw, ${Number(settings.text_line_width) || DEFAULTS.text_line_width}ch)`,
    };
}

function applyStyle(el, settings) {
    const style = captionStyle(settings);
    el.style.setProperty('--caption-size', style['--caption-size']);
    el.style.setProperty('--caption-lines', style['--caption-lines']);
    el.style.maxWidth = style.maxWidth;
}

export function createCaption(root, config = {}) {
    const settings = { ...DEFAULTS, ...config };

    const el = document.createElement('div');
    el.className = 'caption';
    applyStyle(el, settings);
    root.appendChild(el);

    let lastId = null;
    let raf = null;

    const stop = () => {
        if (raf) cancelAnimationFrame(raf);
        raf = null;
    };

    const type = (text) => {
        stop();
        const perChar = Math.max(settings.typing_delay, 0) * 1000;
        const started = performance.now();
        el.classList.add('is-visible');

        const step = (now) => {
            const shown = perChar > 0
                ? Math.min(text.length, Math.floor((now - started) / perChar))
                : text.length;
            el.textContent = text.slice(0, shown);
            if (shown < text.length) raf = requestAnimationFrame(step);
            else raf = null;
        };
        raf = requestAnimationFrame(step);
    };

    return {
        /** A line as it is being said: animate it. */
        say(text, id) {
            if (id && id === lastId) return;
            lastId = id ?? null;
            if (!text) return this.clear();
            type(text);
        },

        /** A line that was already on screen when we connected: no animation. */
        restore(text, id) {
            stop();
            lastId = id ?? null;
            el.textContent = text || '';
            el.classList.toggle('is-visible', Boolean(text));
        },

        clear() {
            stop();
            lastId = null;
            el.textContent = '';
            el.classList.remove('is-visible');
        },

        update(config) {
            Object.assign(settings, config);
            applyStyle(el, settings);
        },
    };
}
