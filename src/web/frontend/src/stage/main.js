/**
 * The browser source: one page that draws whatever the engine says she is.
 *
 * It always renders the caption, and the 3D body only when that is the chosen
 * backend — the renderer is imported dynamically so a PNG setup never downloads
 * three.js at all.
 */

import './stage.css';
import { createCaption } from './caption.js';
import { connect, stageConfig } from './connection.js';

const root = document.getElementById('stage');
const params = new URLSearchParams(window.location.search);

// ?hud=0 hides the connection warning, for the preview inside the dashboard
const quiet = params.get('hud') === '0';
// ?debug=1 logs when each patch lands, in wall-clock ms, to line up with the engine's log
const debug = params.get('debug') === '1';
// ?preview=<model id> draws a model from the library for the dashboard to try on, and never goes live
const preview = params.get('preview');

const config = await stageConfig();
const caption = createCaption(root, config);

let offline = null;
function warn(message) {
    if (quiet) return;
    if (!offline) {
        offline = document.createElement('div');
        offline.className = 'offline';
        root.appendChild(offline);
    }
    offline.textContent = message;
}

function clearWarning() {
    offline?.remove();
    offline = null;
}

function modelUrl(id) {
    // the id is in the url so a new file at the same path is never served from the cache
    return `/stage/model?v=${encodeURIComponent(id || '')}`;
}

let avatar = null;
if (preview) {
    try {
        const { createAvatar } = await import('./avatar.js');
        const url = preview === 'active' ? modelUrl(config.model_id)
            : `/stage/library/models/${encodeURIComponent(preview)}/file`;
        avatar = await createAvatar(root, { ...config, model_url: url });
    } catch (error) {
        console.error('[stage] the preview did not start', error);
        warn(`Preview: ${error.message}`);
    }
} else if (config.avatar_backend === 'png' && config.png_render === 'stage') {
    const { createPngTuber } = await import('./pngtuber.js');
    avatar = createPngTuber(root, config);
} else if (config.avatar_backend === 'model' && config.has_model) {
    try {
        const { createAvatar } = await import('./avatar.js');
        avatar = await createAvatar(root, { ...config, model_url: modelUrl(config.model_id) });
    } catch (error) {
        console.error('[stage] the 3D renderer did not start', error);
        warn(`3D renderer: ${error.message}`);
    }
}

let current = config;

/** Settings were saved. Apply what can be applied; reload for what cannot. */
function applyConfig(next) {
    const before = current;
    current = next;

    // a different backend changes what the page *is* rather than how it draws
    if (next.avatar_backend !== before.avatar_backend
        || next.png_render !== before.png_render
        || next.has_model !== before.has_model
        || (next.model_id !== before.model_id && !avatar?.swapModel)) {
        window.location.reload();
        return;
    }

    caption.update(next);
    avatar?.setLook(next);
    if (next.model_id !== before.model_id) {
        // the old model stays on stage until the new one is ready to be drawn
        avatar.swapModel(modelUrl(next.model_id)).then(clearWarning).catch((error) => {
            console.error('[stage] the new model did not load; keeping the old one', error);
            warn(`New model: ${error.message}`);
        });
    }
}

if (preview) {
    // only the dashboard that opened this page may drive it
    window.addEventListener('message', (event) => {
        if (event.origin !== window.location.origin || event.data?.type !== 'bea-preview') return;
        if (event.data.look) avatar?.setLook({ ...config, ...event.data.look });
        if (event.data.patch) avatar?.apply(event.data.patch, { animate: true });
    });
    // the model has loaded: from here on what the dashboard sends lands
    window.parent?.postMessage({ type: 'bea-preview-ready', ok: Boolean(avatar) }, window.location.origin);
} else {
    connect({
        onStatus: ({ connected }) => (connected ? clearWarning() : warn('Not connected to the engine')),

        // how she looks *now*: put it on screen without acting it out
        onSnapshot: (state) => {
            caption.restore(state.caption, state.caption_id);
            avatar?.apply(state, { animate: false });
        },

        onPatch: (patch) => {
            if (debug) console.debug(`[stage] ${Date.now()} patch`, Object.keys(patch).join(','), patch.mouth_sync || patch.state || '');
            if (patch.config) applyConfig(patch.config);
            if ('caption' in patch) caption.say(patch.caption, patch.caption_id);
            avatar?.apply(patch, { animate: true });
        },
    });
}
