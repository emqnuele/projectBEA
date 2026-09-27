import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EMOTIONS, faceTargets, mouthScale, resolveExpression } from '../src/stage/face.js';

test('the order and names of the emotions are the ones face.py sends', () => {
    assert.deepEqual(EMOTIONS, ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral']);
});

test('intensity scales every emotion and leaves neutral whole', () => {
    const out = faceTargets({ happy: 1, sad: 0.35, neutral: 1 }, 0.7);
    assert.equal(out.happy, 0.7);
    assert.ok(Math.abs(out.sad - 0.245) < 1e-12);
    assert.equal(out.neutral, 1);
    assert.equal(out.angry, 0);
});

test('the proportions between emotions survive the cap', () => {
    const out = faceTargets({ angry: 0.45, sad: 0.35 }, 0.6);
    assert.ok(Math.abs(out.angry / out.sad - 0.45 / 0.35) < 1e-12);
});

test('a missing or broken weight is zero, not NaN', () => {
    const out = faceTargets({ happy: 'x' }, 0.7);
    for (const name of EMOTIONS) assert.ok(Number.isFinite(out[name]));
});

test('the mouth is whole on a neutral face and scaled under a full emotion', () => {
    assert.equal(mouthScale({ neutral: 1 }, 0.5), 1);
    assert.equal(mouthScale({ happy: 1 }, 0.5), 0.5);
    assert.equal(mouthScale({ happy: 0.5 }, 0.5), 0.75);
});

test('two emotions together never scale the mouth past the setting', () => {
    assert.equal(mouthScale({ angry: 0.8, sad: 0.8 }, 0.25), 0.25);
});

test('a setting of one leaves the mouth alone under any face', () => {
    assert.equal(mouthScale({ surprised: 1 }, 1), 1);
});

test('a preset is found by its own name first, then ignoring case', () => {
    assert.equal(resolveExpression(['happy', 'Surprised'], 'happy'), 'happy');
    assert.equal(resolveExpression(['happy', 'Surprised'], 'surprised'), 'Surprised');
    assert.equal(resolveExpression(['happy'], 'surprised'), null);
});
