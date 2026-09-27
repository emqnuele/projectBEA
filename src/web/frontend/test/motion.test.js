import { test } from 'node:test';
import assert from 'node:assert/strict';

import { REST_POSE, baseClipName, baseClipNames, clipFormat, gestureWeight, reanchor, restPose } from '../src/stage/motion.js';

test('every state is carried by the idle clip unless it has its own', () => {
    const config = { idle_clip: 'idle_loop', state_clips: { thinking: 'ponder' } };
    assert.equal(baseClipName('idle', config), 'idle_loop');
    assert.equal(baseClipName('talking', config), 'idle_loop');
    assert.equal(baseClipName('thinking', config), 'ponder');
});

test('no idle clip means the procedural pose, not a missing clip', () => {
    assert.equal(baseClipName('idle', { idle_clip: '' }), REST_POSE);
    assert.equal(baseClipName('idle', {}), REST_POSE);
    assert.equal(baseClipName('idle', { idle_clip: '   ' }), REST_POSE);
});

test('an empty per-state entry falls back to the idle clip', () => {
    assert.equal(baseClipName('listening', { idle_clip: 'idle_loop', state_clips: { listening: '' } }), 'idle_loop');
});

test('the base clips are the ones never played as gestures', () => {
    const names = baseClipNames({ idle_clip: 'idle_loop', state_clips: { thinking: 'ponder', talking: '' } });
    assert.deepEqual([...names].sort(), ['idle_loop', 'ponder']);
});

test('reanchoring moves the first key over the hips and keeps the sway', () => {
    const track = [-0.15, 0.88, 0.03, -0.13, 0.87, 0.04];
    const out = reanchor(track, [0, 0.879, 0.004]);
    assert.ok(Math.abs(out[0] - 0) < 1e-6);
    assert.ok(Math.abs(out[2] - 0.004) < 1e-6);
    // the height is the model's already, and the motion between keys survives
    assert.ok(Math.abs(out[1] - 0.88) < 1e-6);
    assert.ok(Math.abs((out[3] - out[0]) - 0.02) < 1e-6);
    assert.ok(Math.abs((out[5] - out[2]) - 0.01) < 1e-6);
});

test('reanchoring does not touch the array it was given', () => {
    const track = [1, 2, 3];
    reanchor(track, [0, 0, 0]);
    assert.deepEqual(track, [1, 2, 3]);
});

test('a vrm 0.x flips rotations about x and z but not about y', () => {
    const one = restPose('1');
    const zero = restPose('0');
    for (const bone of Object.keys(one)) {
        assert.equal(zero[bone][0], -one[bone][0] || 0);
        assert.equal(zero[bone][1], one[bone][1]);
        assert.equal(zero[bone][2], -one[bone][2] || 0);
    }
    assert.equal(one.leftUpperArm[2], -1.2);
    assert.equal(one.rightUpperArm[2], 1.2);
});

test('a gesture weight gives it exactly its share of the average against the base', () => {
    for (const share of [0, 0.1, 0.25, 0.5, 0.9]) {
        const w = gestureWeight(share);
        assert.ok(Math.abs(w / (1 + w) - share) < 1e-12, `share ${share}`);
    }
});

test('a full gesture is finite and leaves the base almost nothing', () => {
    const w = gestureWeight(1);
    assert.ok(Number.isFinite(w));
    assert.ok(1 / (1 + w) <= 0.001 + 1e-12);
    assert.equal(gestureWeight(-1), 0);
});

test('a clip is told apart by its first bytes, not its name', () => {
    const bytes = (text, tail = []) => Uint8Array.from([...Array.from(text, (c) => c.charCodeAt(0)), ...tail]);
    assert.equal(clipFormat(bytes('glTF', [2, 0, 0, 0])), 'vrma');
    assert.equal(clipFormat(bytes('Kaydara FBX Binary  \0', [0x1a, 0])), 'fbx');
    assert.equal(clipFormat(bytes('; FBX 7.4.0 project file')), null, 'an ascii fbx is not one mixamo sends');
    assert.equal(clipFormat(new Uint8Array(0)), null);
});
