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

let avatar = null;
if (config.avatar_backend === 'model' && config.has_model) {
    try {
        const { createAvatar } = await import('./avatar.js');
        avatar = await createAvatar(root, config);
    } catch (error) {
        console.error('[stage] the 3D renderer did not start', error);
        warn(`3D renderer: ${error.message}`);
    }
}

connect({
    onStatus: ({ connected }) => (connected ? clearWarning() : warn('Not connected to the engine')),

    // how she looks *now*: put it on screen without acting it out
    onSnapshot: (state) => {
        caption.restore(state.caption, state.caption_id);
        avatar?.apply(state, { animate: false });
    },

    onPatch: (patch) => {
        if ('caption' in patch) caption.say(patch.caption, patch.caption_id);
        avatar?.apply(patch, { animate: true });
    },
});
