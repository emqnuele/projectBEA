/**
 * The decisions behind her body, kept free of three.js so node can test them.
 *
 * `body.js` owns the mixer and the actions; everything here is a plain
 * function of config and numbers: which clip carries her in each state, where
 * a clip's hips are moved back to, and the pose she stands in when there is no
 * clip at all.
 */

export const STATES = ['idle', 'listening', 'thinking', 'talking', 'sleeping'];

// the procedural base, used when no idle clip is installed or it fails to load
export const REST_POSE = '';

/** The clip that carries her while she is in `state`, or REST_POSE. */
export function baseClipName(state, config = {}) {
    const perState = config.state_clips || {};
    const own = typeof perState[state] === 'string' ? perState[state].trim() : '';
    if (own) return own;
    return typeof config.idle_clip === 'string' ? config.idle_clip.trim() : REST_POSE;
}

/** Every clip used as a base layer, so the page never plays one as a gesture. */
export function baseClipNames(config = {}) {
    const names = new Set();
    for (const state of STATES) {
        const name = baseClipName(state, config);
        if (name) names.add(name);
    }
    return names;
}

/**
 * Moves a hips position track so its first key sits over the model's own hips.
 *
 * An idle clip is authored on someone else's body and stands 15 cm to one side
 * of ours; the framing is taken from the rest pose, so she would be off centre
 * for the whole stream. Only x and z move: the height is already scaled to the
 * model when the clip is built, and the sway inside the clip is kept.
 */
export function reanchor(values, rest) {
    const out = Float32Array.from(values);
    if (out.length < 3) return out;
    const dx = rest[0] - out[0];
    const dz = rest[2] - out[2];
    for (let i = 0; i + 2 < out.length; i += 3) {
        out[i] += dx;
        out[i + 2] += dz;
    }
    return out;
}

// 1.2 rad about z hangs the upper arm 21° from vertical; about y bends the elbow forward
const ARMS = {
    leftUpperArm: [0, 0, -1.2],
    rightUpperArm: [0, 0, 1.2],
    leftLowerArm: [0, -0.25, 0],
    rightLowerArm: [0, 0.25, 0],
};

/**
 * The euler rotations of the procedural pose, per normalized bone.
 *
 * VRM 0.x is turned 180° about y to face the camera, which flips the sign of
 * every rotation about x and z and leaves y alone.
 */
export function restPose(metaVersion) {
    const flip = metaVersion === '0' ? -1 : 1;
    const out = {};
    for (const [bone, [x, y, z]] of Object.entries(ARMS)) {
        out[bone] = [x * flip || 0, y, z * flip || 0];
    }
    return out;
}

// past this the base keeps a tenth of a percent: 0.01° on a 10° difference, and no infinite weight
const FULL_SHARE = 0.999;

/**
 * The weight that gives a gesture exactly `share` of the bones it animates.
 *
 * The mixer averages a bone's actions by weight; against a base at weight 1, a
 * gesture at s / (1 - s) holds s of the result, and bones it does not animate
 * stay wholly on the base.
 */
export function gestureWeight(share) {
    const s = Math.min(Math.max(share, 0), FULL_SHARE);
    return s / (1 - s);
}

const GLB = [0x67, 0x6c, 0x54, 0x46];
const FBX = Array.from('Kaydara FBX Binary  \0', (c) => c.charCodeAt(0));

/** What a clip file is, from its first bytes: 'vrma', 'fbx' or null. */
export function clipFormat(bytes) {
    const starts = (magic) => magic.every((b, i) => bytes[i] === b);
    if (bytes.length >= GLB.length && starts(GLB)) return 'vrma';
    if (bytes.length >= FBX.length && starts(FBX)) return 'fbx';
    return null;
}
