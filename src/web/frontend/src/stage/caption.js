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

export function createCaption(root, config = {}) {
    const settings = { ...DEFAULTS, ...config };

    const el = document.createElement('div');
    el.className = 'caption';
    el.style.fontSize = `${settings.text_font_size}px`;
    // the box is sized by the configured line width, so the OBS setup and this
    // one wrap at the same place and moving between them changes nothing
    el.style.maxWidth = `${settings.text_line_width}ch`;
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
            el.style.fontSize = `${settings.text_font_size}px`;
            el.style.maxWidth = `${settings.text_line_width}ch`;
        },
    };
}
