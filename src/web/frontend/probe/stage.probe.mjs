// the body on a real vrm, headless: what unit tests cannot see (a t-pose, offsets piling up)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { VRMAnimation, VRMLookAtQuaternionProxy } from '@pixiv/three-vrm-animation';

import { createBody } from '../src/stage/body.js';
import { createLife } from '../src/stage/life.js';
import { animation, armAngle, load, THREE } from './support.mjs';

// fetched by `uv run python tools/fetch_model.py --models-dir <dir> --clips-dir <dir>`
const ASSETS = process.env.BEA_PROBE_ASSETS || '../../../data';
const MODEL = [join(ASSETS, 'AvatarSample_B.vrm'), join(ASSETS, 'models', 'AvatarSample_B.vrm')].find(existsSync);
const IDLE = [join(ASSETS, 'idle_loop.vrma'), join(ASSETS, 'clips', 'idle_loop.vrma')].find(existsSync);
const skip = !MODEL || !IDLE ? 'run `make model` (or set BEA_PROBE_ASSETS) to fetch the model and idle clip' : false;

const dt = 1 / 60;
const tick = () => new Promise((r) => setImmediate(r));

function gesture(z, seconds) {
    const a = new VRMAnimation();
    a.duration = seconds;
    const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, z));
    a.humanoidTracks.rotation.set('rightUpperArm', new THREE.QuaternionKeyframeTrack('x.quaternion', [0, seconds], [...q.toArray(), ...q.toArray()]));
    return a;
}

async function rig({ idle = 'idle_loop', life = false } = {}) {
    const vrm = await load(MODEL);
    const proxy = new VRMLookAtQuaternionProxy(vrm.lookAt);
    proxy.name = 'VRMLookAtQuaternionProxy';
    vrm.scene.add(proxy);
    const scene = new THREE.Scene();
    scene.add(vrm.scene);
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 20);
    camera.position.set(0, 1.35, 1.0);
    const clips = { idle_loop: await animation(IDLE), raise: gesture(1.2, 2), wave: gesture(0.6, 1.5) };
    const body = createBody(vrm, async (name) => {
        if (!clips[name]) throw new Error('no such clip');
        return clips[name];
    }, { idle_clip: idle });
    const lifeLayer = life ? createLife(vrm, camera, scene) : null;
    await new Promise((r) => setTimeout(r, 20));
    return { vrm, body, life: lifeLayer };
}

// the bone's own rotation against the gesture's: the idle still moves the shoulder under it, so the world angle differs
function offGesture(vrm, bone, z) {
    const want = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, z));
    return THREE.MathUtils.radToDeg(vrm.humanoid.getNormalizedBoneNode(bone).quaternion.angleTo(want));
}

async function run(r, seconds, watch) {
    for (let t = 0; t < seconds; t += dt) {
        await tick();
        r.life?.undo();
        r.body.update(dt);
        r.life?.update(dt, { busy: r.body.busy() });
        r.vrm.update(dt);
        watch?.();
    }
}

test('the idle clip keeps her arms down and her hips centred', { skip }, async () => {
    const r = await rig();
    let worst = 0;
    await run(r, 3, () => { worst = Math.max(worst, armAngle(r.vrm, 'left'), armAngle(r.vrm, 'right')); });
    assert.ok(worst < 25, `an arm reached ${worst.toFixed(1)}°`);
    assert.ok(Math.abs(r.vrm.humanoid.getNormalizedBoneNode('hips').position.x) < 0.03);
});

test('a gesture on one arm never drops the other to the t-pose', { skip }, async () => {
    const r = await rig();
    await run(r, 1);
    r.body.play('raise');
    let left = 0;
    let closest = 180;
    await run(r, 3, () => {
        left = Math.max(left, armAngle(r.vrm, 'left'));
        closest = Math.min(closest, offGesture(r.vrm, 'rightUpperArm', 1.2));
    });
    assert.ok(left < 25, `the arm the gesture does not move reached ${left.toFixed(1)}°`);
    assert.ok(closest < 0.5, `the gesture never took hold of its arm: ${closest.toFixed(2)}° off`);
    await run(r, 1);
    assert.ok(offGesture(r.vrm, 'rightUpperArm', 1.2) > 10, 'the gesture did not hand the arm back');
});

test('a gesture cut by another stays within the two', { skip }, async () => {
    const r = await rig();
    await run(r, 1);
    r.body.play('raise');
    await run(r, 0.1);
    r.body.play('wave');
    let left = 0;
    let closest = 180;
    await run(r, 3, () => {
        left = Math.max(left, armAngle(r.vrm, 'left'));
        closest = Math.min(closest, offGesture(r.vrm, 'rightUpperArm', 0.6));
    });
    assert.ok(left < 25);
    assert.ok(closest < 0.5, `the second gesture never took hold: ${closest.toFixed(2)}° off`);
});

test('without an idle clip she stands in the procedural pose, not the t-pose', { skip }, async () => {
    const r = await rig({ idle: '' });
    let worst = 0;
    await run(r, 1, () => { worst = Math.max(worst, armAngle(r.vrm, 'left'), armAngle(r.vrm, 'right')); });
    assert.ok(worst < 22, `an arm reached ${worst.toFixed(1)}°`);
});

test('life rides on the clip and leaves no trace once taken off', { skip }, async () => {
    const withLife = await rig({ life: true });
    const without = await rig();
    for (let t = 0; t < 30; t += dt) {
        withLife.life.undo();
        withLife.body.update(dt);
        withLife.life.update(dt, { loudness: 0.5 });
        withLife.vrm.update(dt);
        without.body.update(dt);
        without.vrm.update(dt);
    }
    withLife.life.undo();
    for (const bone of ['head', 'neck', 'spine', 'chest', 'hips']) {
        const a = withLife.vrm.humanoid.getNormalizedBoneNode(bone).quaternion;
        const b = without.vrm.humanoid.getNormalizedBoneNode(bone).quaternion;
        assert.ok(THREE.MathUtils.radToDeg(a.angleTo(b)) < 0.01, bone);
    }
});

function morph(vrm, name) {
    let out = null;
    vrm.scene.traverse((o) => {
        if (out === null && o.morphTargetDictionary && name in o.morphTargetDictionary) {
            out = o.morphTargetInfluences[o.morphTargetDictionary[name]];
        }
    });
    return out;
}

test('a blink blends under a smile whose eyes are already shut', { skip }, async () => {
    for (const [mode, shut] of [['none', 1], ['blend', 0]]) {
        const vrm = await load(MODEL);
        vrm.expressionManager.getExpression('happy').overrideBlink = mode;
        vrm.expressionManager.setValue('happy', 1);
        vrm.expressionManager.setValue('blink', 1);
        vrm.expressionManager.update();
        assert.equal(morph(vrm, 'Fcl_EYE_Close'), shut, mode);
    }
});
