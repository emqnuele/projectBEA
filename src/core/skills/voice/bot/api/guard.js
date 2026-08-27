// The command API listens on a TCP port. Even on loopback that is one
// container or one careless bind away from the network, so every route needs
// the shared secret the python transport minted for this process.

const crypto = require('node:crypto');

// smallest sensible bound: an invite that never expires is a permanent door
const DEFAULT_MAX_AGE = 3600;
const DEFAULT_MAX_USES = 1;
const FALLBACK_MAX_AGE = 86400;
const FALLBACK_MAX_USES = 10;

function timingSafeEqual(a, b) {
    const ba = Buffer.from(a || '', 'utf8');
    const bb = Buffer.from(b || '', 'utf8');
    if (ba.length !== bb.length) return false;
    return crypto.timingSafeEqual(ba, bb);
}

function bearer(headers) {
    const raw = (headers && (headers.authorization || headers.Authorization)) || '';
    const [scheme, ...rest] = String(raw).split(' ');
    if (scheme.toLowerCase() !== 'bearer') return '';
    return rest.join(' ').trim();
}

// express middleware. Without a configured secret it refuses everything: an
// open API is a worse outcome than a broken one.
function requireToken(expected) {
    return (req, res, next) => {
        if (!expected) {
            console.error('[guard] API_TOKEN is not set; refusing every request.');
            return res.status(503).json({ error: 'API token not configured' });
        }
        if (!timingSafeEqual(bearer(req.headers), expected)) {
            console.warn(`[guard] Refused an unauthenticated request to ${req.path}`);
            return res.status(401).json({ error: 'Unauthorized' });
        }
        return next();
    };
}

function positiveInt(raw, fallback, cap) {
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n) || n <= 0) return fallback;
    return cap ? Math.min(n, cap) : n;
}

// discord reads 0 as "forever" / "unlimited" for both of these, so 0 is not a
// value we ever pass through
function inviteOptions(env = {}) {
    return {
        maxAge: positiveInt(env.INVITE_MAX_AGE, DEFAULT_MAX_AGE) || FALLBACK_MAX_AGE,
        maxUses: positiveInt(env.INVITE_MAX_USES, DEFAULT_MAX_USES) || FALLBACK_MAX_USES,
    };
}

module.exports = { requireToken, inviteOptions, bearer };
