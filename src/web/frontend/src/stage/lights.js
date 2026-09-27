/**
 * How she is lit, as plain data node can test. `avatar.js` turns an entry into
 * three.js lights.
 *
 * `flat` is the original rig, one key light and an even ambient, kept as the
 * default so a saved setup looks the way it always did. `soft` and `studio`
 * add a fill and, for `studio`, a light from behind and a rim on the MToon
 * materials. Their numbers are a starting point to judge in the preview.
 *
 * Positions are metres around her, +z towards the camera. `rim` is the MToon
 * parametric rim: colour, fresnel power, lift.
 */

export const LIGHT_PRESETS = {
    flat: {
        lights: [
            { type: 'directional', color: '#ffffff', intensity: 2.0, position: [1, 2, 1.5] },
            { type: 'ambient', color: '#ffffff', intensity: 1.1 },
        ],
        rim: null,
    },
    soft: {
        lights: [
            { type: 'directional', color: '#fff6ee', intensity: 1.6, position: [1, 2, 1.5] },
            { type: 'directional', color: '#e8eeff', intensity: 0.6, position: [-1.5, 1, 1] },
            { type: 'hemisphere', color: '#ffffff', ground: '#b9b4c8', intensity: 0.9 },
            { type: 'ambient', color: '#ffffff', intensity: 0.3 },
        ],
        rim: null,
    },
    studio: {
        lights: [
            { type: 'directional', color: '#ffffff', intensity: 2.2, position: [1.2, 1.8, 1.2] },
            { type: 'directional', color: '#dfe6ff', intensity: 0.5, position: [-1.5, 0.8, 1] },
            { type: 'directional', color: '#ffffff', intensity: 1.4, position: [0, 1.5, -2] },
            { type: 'ambient', color: '#ffffff', intensity: 0.6 },
        ],
        rim: { color: '#3a3f55', power: 3, lift: 0.1 },
    },
};

export const DEFAULT_LIGHTS = 'flat';

/** The preset by name; anything unknown is the default. */
export function lightPreset(name) {
    return LIGHT_PRESETS[name] || LIGHT_PRESETS[DEFAULT_LIGHTS];
}
