/**
 * What she does when nothing is happening.
 *
 * A body that only moves when it is spoken to is the thing that breaks the
 * illusion fastest — faster than any latency, because it is on screen the whole
 * time. She blinks, she breathes, her eyes drift and her head follows them a
 * beat later. None of it is animation data: it is a handful of slow sines and
 * an exponential ease, so it costs nothing in a browser source and never has to
 * be authored per model.
 *
 * Two rules hold the whole file together:
 *
 *  - Nothing here is keyframed. Every target is eased with the same
 *    `k = 1 - exp(-rate * dt)` the expressions use, so it is frame-rate
 *    independent and never arrives with a snap.
 *  - The eyes lead and the head follows. That single lag is most of what
 *    separates "looking at you" from "aimed at you".
 *
 * A behaviour clip owns the body while it plays, so the sway steps out of its
 * way and eases back in afterwards rather than fighting the mixer for the same
 * bones.
 */

import * as THREE from 'three';

// how long the head takes to arrive where the eyes already are. The lag is the
// point: eyes that lead and a head that follows is most of what separates
// "looking at you" from "aimed at you".
const HEAD_RATE = 2.2;

// how fast the sway hands the body back after a behaviour has finished with it
const SWAY_RATE = 3;

// a blink is fast to close and slower to open; a symmetrical one reads as a wink
const BLINK_SECONDS = 0.16;
const BLINK_CLOSE = 0.35;

/** How she carries herself in each state the engine can put her in. */
const STATES = {
    // watching the room, moving enough to be alive and not enough to distract
    idle: { gaze: 0.16, drift: 0.09, blink: [2.5, 6.5], sway: 1, breath: 1, eyesShut: 0 },

    // attention on whoever is talking: less wandering, and blinking a little more
    listening: { gaze: 0.06, drift: 0.05, blink: [2, 4.5], sway: 0.7, breath: 1, eyesShut: 0 },

    // she is the one talking, so the head moves with the line rather than around it
    talking: { gaze: 0.1, drift: 0.14, blink: [2.5, 6], sway: 1.15, breath: 1.15, eyesShut: 0 },

    // asleep: eyes shut, and only the breathing left
    sleeping: { gaze: 0, drift: 0, blink: [99, 99], sway: 0.35, breath: 0.7, eyesShut: 1 },
};

const DEFAULT_STATE = STATES.idle;

/**
 * @param vrm    the loaded VRM
 * @param camera what she looks at when she is looking at anyone
 * @param scene  where the gaze target lives, so it is transformed with everything else
 */
export function createLife(vrm, camera, scene) {
    const bone = (name) => vrm.humanoid?.getNormalizedBoneNode(name)
        || vrm.humanoid?.getRawBoneNode(name);

    const head = bone('head');
    const chest = bone('chest') || bone('upperChest') || bone('spine');
    const spine = bone('spine');
    const hips = bone('hips');

    // where each swayed bone sits with nothing applied. Read once, because from
    // the second frame on what is there is whatever this file last wrote.
    const rest = new Map();
    for (const node of [head, chest, spine, hips]) {
        if (node) rest.set(node, node.rotation.clone());
    }

    // the point the eyes are aimed at. An Object3D rather than the camera
    // itself so it can be moved off her line of sight without moving the shot.
    const target = new THREE.Object3D();
    scene.add(target);
    if (vrm.lookAt) vrm.lookAt.target = target;

    // her own clock, so two models on one page are never in step
    let t = Math.random() * 1000;
    let state = DEFAULT_STATE;

    let blinkIn = 1 + Math.random() * 3;
    let blinking = 0;
    // how far the eyes are shut by sleeping; eased both ways so waking up is a
    // lid slowly lifting, not a snap to a resting face
    let lids = 0;

    // 0 while a behaviour owns the body, easing back to 1 when it lets go
    let sway = 1;

    const gaze = new THREE.Vector3();
    const facing = { yaw: 0, pitch: 0 };
    const wanted = { yaw: 0, pitch: 0 };

    function ease(from, to, rate, dt) {
        return THREE.MathUtils.lerp(from, to, 1 - Math.exp(-rate * dt));
    }

    /** Where she is looking, as an offset from the camera in metres. */
    function aim() {
        // three sines whose periods do not divide into each other: the drift
        // never repeats, which is what stops it reading as a loop
        const x = Math.sin(t * 0.31) * 0.6 + Math.sin(t * 0.13) * 0.4;
        const y = Math.sin(t * 0.23) * 0.5 + Math.sin(t * 0.07) * 0.5;
        gaze.copy(camera.position);
        gaze.x += x * state.drift;
        gaze.y += y * state.drift * 0.6;
        return gaze;
    }

    function blink(dt) {
        const manager = vrm.expressionManager;
        if (!manager) return;

        if (state.eyesShut) {
            lids = ease(lids, 1, 4, dt);
            manager.setValue('blink', lids);
            return;
        }

        // a waking pair of eyelids still holds the sleep value; let it open
        // slowly, and keep voluntary blinks off it until it has
        if (lids > 0) {
            lids = ease(lids, 0, 3, dt);
            manager.setValue('blink', lids);
            return;
        }

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
            shut = gone < BLINK_CLOSE
                ? gone / BLINK_CLOSE
                : 1 - (gone - BLINK_CLOSE) / (1 - BLINK_CLOSE);
        }
        manager.setValue('blink', shut);
    }

    /**
     * Moves a bone towards rest plus an offset, by however much of it is ours.
     *
     * Towards rather than onto, because `sway` is exactly the fraction of this
     * bone the idle motion currently owns: a gesture fading out still has the
     * rest of it, and writing an absolute value would cut its fade off.
     */
    function put(node, x, y, z) {
        if (!node) return;
        const base = rest.get(node);
        node.rotation.set(
            THREE.MathUtils.lerp(node.rotation.x, base.x + x, sway),
            THREE.MathUtils.lerp(node.rotation.y, base.y + y, sway),
            THREE.MathUtils.lerp(node.rotation.z, base.z + z, sway),
        );
    }

    function follow(dt) {
        if (!head) return;
        // the head is aimed at the same point as the eyes, but reaches it later
        const to = aim();
        const at = head.getWorldPosition(new THREE.Vector3());
        wanted.yaw = Math.atan2(to.x - at.x, to.z - at.z) * state.gaze;
        wanted.pitch = -Math.atan2(to.y - at.y, Math.abs(to.z - at.z)) * state.gaze;

        facing.yaw = ease(facing.yaw, wanted.yaw, HEAD_RATE, dt);
        facing.pitch = ease(facing.pitch, wanted.pitch, HEAD_RATE, dt);
        put(head, facing.pitch, facing.yaw, 0);
    }

    function breathe() {
        // one slow rise and fall through the chest, and a weight shift under it
        // half as fast, so she is never quite square to the camera
        const breath = Math.sin(t * 1.6) * 0.012 * state.breath;
        const shift = Math.sin(t * 0.37) * 0.02 * state.sway;
        const lean = Math.sin(t * 0.29) * 0.014 * state.sway;

        if (chest && chest !== spine) put(chest, -breath, 0, 0);
        if (spine) put(spine, breath * 0.5, shift, lean);
        put(hips, 0, -shift * 0.4, -lean * 0.5);
    }

    return {
        /** The engine's word for what she is doing. Unknown states read as idle. */
        setState(name) {
            state = STATES[name] || DEFAULT_STATE;
        },

        /**
         * @param dt      seconds since the last frame
         * @param busy    a behaviour clip is driving the body right now
         */
        update(dt, busy) {
            t += dt;
            // eyes first: they are the only thing here a clip does not touch
            if (vrm.lookAt) target.position.copy(aim());
            blink(dt);

            // a gesture owns the body while it plays; this is how much of it is
            // back, and it is what every write below is weighted by
            sway = ease(sway, busy ? 0 : 1, SWAY_RATE, dt);
            if (sway < 0.001) return;
            follow(dt);
            breathe();
        },

        /** The eyes, at rest, on the frame a reconnecting page draws first. */
        settle() {
            if (vrm.lookAt) target.position.copy(camera.position);
            facing.yaw = 0;
            facing.pitch = 0;
        },
    };
}
