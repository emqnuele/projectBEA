/**
 * Her body: one mixer, a base layer that never stops, and gestures on top.
 *
 * three.js mixes the actions on a bone as a weighted average, and hands any
 * weight below one to the bone's original value — on a VRM, the T-pose. So:
 *
 *  - the base action (the idle clip, or a procedural pose) always holds weight
 *    one, and always covers the arms, so no bone is ever left short;
 *  - a gesture is never crossfaded against the base, which would fade the base
 *    out on every bone while the gesture only claims the bones it animates. It
 *    is laid over it at weight f / (1 - f): on its own bones that is exactly a
 *    share f of the average, and every other bone stays wholly on the base.
 */

import * as THREE from 'three';
import { createVRMAnimationClip } from '@pixiv/three-vrm-animation';

import { REST_POSE, baseClipName, baseClipNames, gestureWeight, reanchor, restPose } from './motion.js';

const GESTURE_IN = 0.25;
const GESTURE_OUT = 0.3;
const BASE_SWAP = 0.5;

/**
 * @param vrm            the loaded VRM
 * @param loadAnimation  (name, vrm) -> Promise of a VRMAnimation, or of a clip already retargeted to `vrm`
 * @param config         `idle_clip` and `state_clips`, as `/stage/config` sends them
 */
export function createBody(vrm, loadAnimation, config = {}) {
    const mixer = new THREE.AnimationMixer(vrm.scene);
    const hips = vrm.humanoid?.getNormalizedBoneNode('hips');
    const restHips = hips ? hips.position.toArray() : null;
    const pose = restPoseTracks();

    // a vrm animation becomes a different clip as a base (arms merged in) than as a gesture
    const bases = new Map();
    const gestures = new Map();

    let settings = pick(config);
    let state = 'idle';
    let base = null;
    let baseGeneration = 0;
    let gestureGeneration = 0;
    // every gesture still holding weight: {action, share, target, rate}
    const layers = [];
    // bases faded out, stopped once they hold no weight: stopping one mid-fade drops to the t-pose
    const leaving = new Set();

    function pick(next) {
        return { idle_clip: next.idle_clip ?? '', state_clips: next.state_clips || {} };
    }

    function restPoseTracks() {
        const tracks = [];
        for (const [bone, euler] of Object.entries(restPose(vrm.meta?.metaVersion))) {
            const node = vrm.humanoid?.getNormalizedBoneNode(bone);
            if (!node) continue;
            const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(...euler));
            tracks.push(new THREE.QuaternionKeyframeTrack(`${node.name}.quaternion`, [0], q.toArray()));
        }
        return tracks;
    }

    function anchored(clip) {
        if (!restHips || !hips) return clip;
        for (const track of clip.tracks) {
            if (track.name === `${hips.name}.position`) track.values = reanchor(track.values, restHips);
        }
        return clip;
    }

    function asBase(clip) {
        const covered = new Set(clip.tracks.map((track) => track.name));
        for (const track of pose) {
            if (!covered.has(track.name)) clip.tracks.push(track.clone());
        }
        return clip;
    }

    async function clipNamed(name) {
        const loaded = await loadAnimation(name, vrm);
        return loaded instanceof THREE.AnimationClip ? loaded : createVRMAnimationClip(loaded, vrm);
    }

    async function baseClip(name) {
        if (name === REST_POSE) {
            if (!bases.has(REST_POSE)) bases.set(REST_POSE, new THREE.AnimationClip('rest-pose', 1, pose.map((t) => t.clone())));
            return bases.get(REST_POSE);
        }
        if (!bases.has(name)) bases.set(name, asBase(anchored(await clipNamed(name))));
        return bases.get(name);
    }

    async function gestureClip(name) {
        if (!gestures.has(name)) gestures.set(name, anchored(await clipNamed(name)));
        return gestures.get(name);
    }

    async function settleBase() {
        const name = baseClipName(state, settings);
        const generation = ++baseGeneration;
        let clip;
        try {
            clip = await baseClip(name);
        } catch (error) {
            console.warn(`[stage] base clip "${name}" did not load, standing in the procedural pose:`, error.message);
            clip = await baseClip(REST_POSE);
        }
        // a newer state or config arrived while this one was loading
        if (generation !== baseGeneration) return;

        const next = mixer.clipAction(clip);
        if (next === base) return;
        next.setLoop(THREE.LoopRepeat, Infinity);
        leaving.delete(next);
        next.enabled = true;
        next.setEffectiveWeight(1);
        next.play();
        const previous = base;
        base = next;
        if (previous) {
            previous.crossFadeTo(next, BASE_SWAP, false);
            leaving.add(previous);
        }
    }

    function layerOf(action) {
        return layers.find((layer) => layer.action === action);
    }

    mixer.addEventListener('finished', (event) => {
        const layer = layerOf(event.action);
        if (!layer) return;
        layer.target = 0;
        layer.rate = 1 / GESTURE_OUT;
    });

    // the procedural pose is synchronous, so she is never drawn in the t-pose while the idle clip loads
    base = mixer.clipAction(new THREE.AnimationClip('rest-pose', 1, pose.map((t) => t.clone())));
    bases.set(REST_POSE, base.getClip());
    base.setLoop(THREE.LoopRepeat, Infinity);
    base.play();
    settleBase();

    return {
        mixer,

        /** One-shot behaviour, laid over the base. A base clip is never played as one. */
        async play(name) {
            if (!name || baseClipNames(settings).has(name)) return;
            // the request that started last is the one that belongs on stage, whichever loads first
            const generation = ++gestureGeneration;
            let clip;
            try {
                clip = await gestureClip(name);
            } catch (error) {
                console.warn(`[stage] behaviour "${name}" did not play:`, error.message);
                return;
            }
            if (generation !== gestureGeneration) return;

            for (const layer of layers) {
                layer.target = 0;
                layer.rate = 1 / GESTURE_IN;
            }
            const action = mixer.clipAction(clip);
            action.setLoop(THREE.LoopOnce, 1);
            action.clampWhenFinished = true;
            action.reset();
            action.play();
            let layer = layerOf(action);
            if (!layer) {
                const gaze = clip.tracks.some((track) => track.name.startsWith('VRMLookAtQuaternionProxy.'));
                layer = { action, share: 0, gaze };
                layers.push(layer);
            }
            layer.target = 1;
            layer.rate = 1 / GESTURE_IN;
            action.setEffectiveWeight(gestureWeight(layer.share));
        },

        setState(next) {
            if (next === state) return;
            state = next;
            settleBase();
        },

        setConfig(next = {}) {
            settings = pick(next);
            settleBase();
        },

        /** How much of the body a gesture holds right now, 0 to 1. */
        busy() {
            return layers.reduce((most, layer) => Math.max(most, layer.share), 0);
        },

        /** How much of the gaze a gesture that drives the eyes holds, 0 to 1. */
        gazeShare() {
            return layers.reduce((most, layer) => (layer.gaze ? Math.max(most, layer.share) : most), 0);
        },

        update(dt) {
            for (let i = layers.length - 1; i >= 0; i -= 1) {
                const layer = layers[i];
                const step = layer.rate * dt;
                layer.share = layer.target > layer.share
                    ? Math.min(layer.target, layer.share + step)
                    : Math.max(layer.target, layer.share - step);
                if (layer.share === 0 && layer.target === 0) {
                    layer.action.stop();
                    layers.splice(i, 1);
                } else {
                    layer.action.setEffectiveWeight(gestureWeight(layer.share));
                }
            }
            mixer.update(dt);
            for (const action of leaving) {
                if (action === base) {
                    leaving.delete(action);
                } else if (!action.enabled || action.getEffectiveWeight() === 0) {
                    action.stop();
                    leaving.delete(action);
                }
            }
        },
    };
}
