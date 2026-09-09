/**
 * The browser source: one page that draws whatever the engine says she is.
 *
 * For now it renders the caption; the body arrives behind the same connection.
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

connect({
    onStatus: ({ connected }) => (connected ? clearWarning() : warn('Not connected to the engine')),

    // how she looks *now*: put it on screen without acting it out
    onSnapshot: (state) => {
        caption.restore(state.caption, state.caption_id);
    },

    onPatch: (patch) => {
        if ('caption' in patch) caption.say(patch.caption, patch.caption_id);
    },
});
