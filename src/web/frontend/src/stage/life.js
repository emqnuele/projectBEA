/**
 * What she does on top of whatever her body is playing.
 *
 * A body that only moves when it is spoken to is the thing that breaks the
 * illusion fastest, because it is on screen the whole time. She blinks, she
 * breathes, her eyes jump and drift and her head follows them a beat later;
 * listening she nods, thinking she looks away, talking her head dips with her
 * own voice. None of it is animation data, and none of it is authored per model.
 *
 * Everything here is an offset laid over the pose the mixer wrote this frame,
 * never a pose of its own: writing absolute rotations would erase the idle clip
 * underneath. `undo()` takes last frame's offsets back off before the mixer runs,
 * because the mixer only writes a bone whose value changed and would otherwise
 * leave them to pile up.
 */

import * as THREE from 'three';

import { nodCurve, nodWait, saccadeOffset, saccadeWait, stateNamed } from './states.js';

// how fast a new state's numbers replace the old ones, so a change of state is a shift, not a jump
const STATE_RATE = 3;

// a blink is fast to close and slower to open; a symmetrical one reads as a wink
const BLINK_SECONDS = 0.16;
const BLINK_CLOSE = 0.35;

// how much of the head's motion survives while a gesture holds the body, so the two do not add up
const GESTURE_DAMPING = 0.5;

// how fast her head follows the loudness of her voice: a dip per word, not per sample
const VOICE_RATE = 10;

const BONES = ['head', 'chest', 'spine', 'hips'];
const EASED = ['wander', 'head', 'headRate', 'breath', 'sway', 'voice', 'droop'];

function ease(from, to, rate, dt) {
    return THREE.MathUtils.lerp(from, to, 1 - Math.exp(-rate * dt));
}

/** Rotations applied on top of the mixer, and taken back off before it runs again. */
export function createOffsets(vrm, names) {
    // vrm 0.x is turned 180° about y, which reverses rotations about x and z (measured)
    const flip = vrm.meta?.metaVersion === '0' ? -1 : 1;
    const nodes = new Map();
    for (const name of names) {
        const node = vrm.humanoid?.getNormalizedBoneNode(name);
        if (node) nodes.set(name, { node, applied: new THREE.Quaternion() });
    }
    const q = new THREE.Quaternion();
    const e = new THREE.Euler();
    return {
        undo() {
            for (const entry of nodes.values()) {
                entry.node.quaternion.multiply(q.copy(entry.applied).invert());
                entry.applied.identity();
            }
        },
        add(name, x, y, z) {
            const entry = nodes.get(name);
            if (!entry) return;
            q.setFromEuler(e.set(x * flip, y, z * flip));
            entry.node.quaternion.multiply(q);
            entry.applied.multiply(q);
        },
        has(name) {
            return nodes.has(name);
        },
    };
}

/**
 * @param vrm    the loaded VRM
 * @param camera what she looks at when she is looking at anyone
 * @param scene  where the gaze target lives, so it is transformed with everything else
 */
export function createLife(vrm, camera, scene) {
    const offsets = createOffsets(vrm, BONES);
    const head = vrm.humanoid?.getNormalizedBoneNode('head');
    const spineName = offsets.has('chest') ? 'chest' : 'spine';

    // the point the eyes are aimed at, moved off the camera without moving the shot
    const target = new THREE.Object3D();
    scene.add(target);
    if (vrm.lookAt) vrm.lookAt.target = target;

    // her own clock, so two models on one page are never in step
    let t = Math.random() * 1000;
    let state = stateNamed('idle');
    const now = Object.fromEntries(EASED.map((key) => [key, state[key]]));
    const look = [...state.look];

    let blinkIn = 1 + Math.random() * 3;
    let blinking = 0;
    // eyelids shut by sleep, eased both ways so waking up is a lid lifting, not a snap
    let lids = 0;

    let saccadeIn = 0;
    const saccade = [0, 0];

    let nodIn = 1;
    let nodAt = -1;

    let voice = 0;

    const focus = new THREE.Vector3();
    const eye = new THREE.Vector3();
    const at = new THREE.Vector3();
    const facing = { yaw: 0, pitch: 0 };

    function aimFocus() {
        // two sines per axis whose periods never line up, so the drift never reads as a loop
        const x = Math.sin(t * 0.31) * 0.6 + Math.sin(t * 0.13) * 0.4;
        const y = Math.sin(t * 0.23) * 0.5 + Math.sin(t * 0.07) * 0.5;
        focus.copy(camera.position);
        focus.x += look[0] + x * now.wander;
        focus.y += look[1] + y * now.wander * 0.6;
        return focus;
    }

    function blink(dt) {
        const manager = vrm.expressionManager;
        if (!manager) return;

        if (state.eyesShut) {
            lids = ease(lids, 1, 4, dt);
            manager.setValue('blink', lids);
            return;
        }
        if (lids > 0.001) {
            lids = ease(lids, 0, 3, dt);
            manager.setValue('blink', lids);
            return;
        }
        lids = 0;

        blinkIn -= dt;
        if (blinkIn <= 0 && blinking <= 0) {
            const [low, high] = state.blink;
            blinkIn = low + Math.random() * (high - low);
            blinking = BLINK_SECONDS;
        }
        let shut = 0;
        if (blinking > 0) {
            blinking = Math.max(0, blinking - dt);
            const gone = 1 - blinking / BLINK_SECONDS;
            shut = gone < BLINK_CLOSE ? gone / BLINK_CLOSE : 1 - (gone - BLINK_CLOSE) / (1 - BLINK_CLOSE);
        }
        manager.setValue('blink', shut);
    }

    function eyes(dt) {
        if (!vrm.lookAt) return;
        eye.copy(focus);
        if (state.saccade) {
            saccadeIn -= dt;
            if (saccadeIn <= 0) {
                const [yaw, pitch] = saccadeOffset(state.saccade.radius, Math.random(), Math.random());
                saccade[0] = yaw;
                saccade[1] = pitch;
                saccadeIn = saccadeWait(state.saccade, Math.random());
            }
            // degrees at the distance to the focus, so a jump is the same angle in any shot
            const distance = head ? head.getWorldPosition(at).distanceTo(focus) : 1;
            eye.x += Math.tan(THREE.MathUtils.degToRad(saccade[0])) * distance;
            eye.y += Math.tan(THREE.MathUtils.degToRad(saccade[1])) * distance;
        }
        target.position.copy(eye);
    }

    function nod(dt) {
        const spec = state.nod;
        if (!spec) {
            nodAt = -1;
            return 0;
        }
        if (nodAt >= 0) {
            nodAt += dt;
            if (nodAt >= spec.length) nodAt = -1;
        } else {
            nodIn -= dt;
            if (nodIn <= 0) {
                nodAt = 0;
                nodIn = nodWait(spec, Math.random());
            }
        }
        return nodAt >= 0 ? spec.depth * nodCurve(nodAt, spec.length) : 0;
    }

    function turnHead(dt, damping, loudness) {
        if (!head) return;
        head.getWorldPosition(at);
        const wantYaw = Math.atan2(focus.x - at.x, focus.z - at.z) * now.head;
        const wantPitch = -Math.atan2(focus.y - at.y, Math.abs(focus.z - at.z)) * now.head;
        facing.yaw = ease(facing.yaw, wantYaw, now.headRate, dt);
        facing.pitch = ease(facing.pitch, wantPitch, now.headRate, dt);

        voice = ease(voice, loudness, VOICE_RATE, dt);
        const dip = nod(dt) + voice * now.voice + now.droop;
        offsets.add('head', (facing.pitch + dip) * damping, facing.yaw * damping, 0);
    }

    function breathe() {
        // one slow rise and fall through the chest, and a weight shift under it half as fast
        const breath = Math.sin(t * 1.6) * 0.012 * now.breath;
        const shift = Math.sin(t * 0.37) * 0.02 * now.sway;
        const lean = Math.sin(t * 0.29) * 0.014 * now.sway;
        if (spineName === 'chest') offsets.add('chest', -breath, 0, 0);
        offsets.add('spine', breath * 0.5, shift, lean);
        offsets.add('hips', 0, -shift * 0.4, -lean * 0.5);
    }

    return {
        /** Takes last frame's offsets off, so the mixer and this never add up. Call before the mixer. */
        undo() {
            offsets.undo();
        },

        /** The engine's word for what she is doing. Unknown states read as idle. */
        setState(name) {
            const next = stateNamed(name);
            if (next === state) return;
            state = next;
            // the next saccade and nod follow the new state's rhythm, not the old one's
            saccadeIn = 0;
            nodIn = state.nod ? nodWait(state.nod, Math.random()) : 1;
        },

        /**
         * @param dt       seconds since the last frame
         * @param busy     how much of the body a gesture holds, 0 to 1
         * @param loudness how open her mouth is right now, 0 to 1
         * @param gazeClip how much of the gaze a gesture drives, 0 to 1
         */
        update(dt, { busy = 0, loudness = 0, gazeClip = 0 } = {}) {
            t += dt;
            for (const key of EASED) now[key] = ease(now[key], state[key], STATE_RATE, dt);
            look[0] = ease(look[0], state.look[0], STATE_RATE, dt);
            look[1] = ease(look[1], state.look[1], STATE_RATE, dt);

            aimFocus();
            eyes(dt);
            // past halfway the clip's own gaze wins outright; the eyes changing owner reads as one more saccade
            if (vrm.lookAt) vrm.lookAt.autoUpdate = gazeClip < 0.5;
            blink(dt);
            turnHead(dt, 1 - GESTURE_DAMPING * busy, loudness);
            breathe();
        },

        /** Lets go of what this file added to the scene. */
        dispose() {
            scene.remove(target);
            if (vrm.lookAt) vrm.lookAt.target = null;
        },

        /** The eyes at rest, on the frame a reconnecting page draws first. */
        settle() {
            aimFocus();
            target.position.copy(focus);
            facing.yaw = 0;
            facing.pitch = 0;
            voice = 0;
        },
    };
}
