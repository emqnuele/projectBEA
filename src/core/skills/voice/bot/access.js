// Who reaches Bea at all.
//
// The whitelist used to be a wall: someone not on it produced no perception,
// no roster entry, no chance of ever becoming someone she knows. Her whole
// memory is built on meeting people and promoting them over time, and this
// switched that off on the one platform where she has a voice.

const ACCESS_MODES = Object.freeze(['strict', 'boost', 'open']);

const DEFAULT_MODE = 'strict';

// mode -> may an unlisted person reach her at all?
function mayReach(mode, whitelisted) {
    if (whitelisted) return true;
    // anything unrecognised falls back to the closed door, never the open one
    return mode === 'boost' || mode === 'open';
}

function normalizeMode(raw) {
    const mode = String(raw || '').trim().toLowerCase();
    return ACCESS_MODES.includes(mode) ? mode : DEFAULT_MODE;
}

module.exports = { mayReach, normalizeMode, ACCESS_MODES, DEFAULT_MODE };
