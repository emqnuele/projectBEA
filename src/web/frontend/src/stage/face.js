/**
 * The arithmetic of her face, kept free of three.js so node can test it.
 *
 * The engine sends full-strength weights (`face.py`); how strong a face reads on
 * a given model is a property of the model and of taste, so it is scaled here,
 * where it can be tuned live without touching what the engine means by a mood.
 */

export const EMOTIONS = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral'];

/** The weights to ease towards: every emotion scaled by `intensity`, neutral left whole. */
export function faceTargets(weights, intensity = 1) {
    const out = {};
    for (const name of EMOTIONS) {
        const w = Number(weights?.[name]) || 0;
        out[name] = name === 'neutral' ? w : w * intensity;
    }
    return out;
}

/**
 * How much of the mouth's opening survives under the face she is wearing.
 *
 * VRoid's emotion shapes already move the mouth, and the visemes add on top of
 * them; the stronger the emotion, the more the lip sync is scaled towards
 * `underEmotion`.
 */
export function mouthScale(current, underEmotion = 1) {
    let emotion = 0;
    for (const name of EMOTIONS) {
        if (name !== 'neutral') emotion += Number(current?.[name]) || 0;
    }
    const k = Math.min(Math.max(emotion, 0), 1);
    return 1 + (underEmotion - 1) * k;
}

/**
 * The model's own name for a preset, or null.
 *
 * VRM 0.x has no `surprised` preset, and VRoid exports it as a custom group
 * called "Surprised", which three-vrm keeps under that exact name.
 */
export function resolveExpression(available, wanted) {
    if (available.includes(wanted)) return wanted;
    const lower = wanted.toLowerCase();
    return available.find((name) => name.toLowerCase() === lower) ?? null;
}
