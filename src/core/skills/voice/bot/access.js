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

// Who may run a `!command`. Pure: no discord, no whitelist file, no replies.
// The owner is the admin and runs everything; everyone else needs the
// whitelist for ordinary commands and never touches admin ones.
function checkCommandAccess({ category, isOwner, whitelisted }) {
    if (isOwner) return { allowed: true, reason: 'owner' };
    if (category === 'admin') return { allowed: false, reason: 'owner-only' };
    if (whitelisted) return { allowed: true, reason: 'whitelisted' };
    return { allowed: false, reason: 'not-whitelisted' };
}

module.exports = { mayReach, normalizeMode, checkCommandAccess, ACCESS_MODES, DEFAULT_MODE };
