import { test } from 'node:test';
import assert from 'node:assert/strict';

import { STATES, nodCurve, nodWait, saccadeOffset, saccadeWait, stateNamed } from '../src/stage/states.js';

const KEYS = Object.keys(STATES.idle).sort();

test('every state the engine sends has a posture, thinking included', () => {
    for (const name of ['idle', 'listening', 'thinking', 'talking', 'sleeping']) {
        assert.ok(STATES[name], name);
        assert.deepEqual(Object.keys(STATES[name]).sort(), KEYS, `${name} is missing a knob`);
    }
});

test('an unknown state reads as idle', () => {
    assert.equal(stateNamed('dancing'), STATES.idle);
});

test('asleep, the eyes stay shut and do not jump', () => {
    assert.equal(STATES.sleeping.eyesShut, 1);
    assert.equal(STATES.sleeping.saccade, null);
    assert.ok(STATES.sleeping.droop > 0);
});

test('thinking looks away and lets the head lag further behind the eyes', () => {
    const [right, up] = STATES.thinking.look;
    assert.ok(up > 0 && right !== 0);
    assert.ok(STATES.thinking.headRate < STATES.idle.headRate);
    assert.ok(STATES.thinking.blink[0] > STATES.idle.blink[0]);
});

test('only listening nods, and only talking follows her voice', () => {
    for (const [name, s] of Object.entries(STATES)) {
        assert.equal(Boolean(s.nod), name === 'listening', name);
        assert.equal(s.voice > 0, name === 'talking', name);
    }
});

test('a saccade never comes sooner than its gap and averages its mean', () => {
    const saccade = STATES.idle.saccade;
    let total = 0;
    const n = 20000;
    for (let i = 0; i < n; i += 1) {
        const wait = saccadeWait(saccade, (i + 0.5) / n);
        assert.ok(wait >= saccade.gap);
        total += wait;
    }
    assert.ok(Math.abs(total / n - saccade.mean) < 0.02, `mean ${total / n}`);
});

test('a draw of one does not produce an infinite wait', () => {
    assert.ok(Number.isFinite(saccadeWait(STATES.idle.saccade, 1)));
});

test('a saccade lands inside its radius', () => {
    for (const [u, v] of [[0, 0], [1, 0], [1, 0.25], [0.5, 0.7]]) {
        const [x, y] = saccadeOffset(4, u, v);
        assert.ok(Math.hypot(x, y) <= 4 + 1e-9);
    }
    assert.ok(Math.abs(Math.hypot(...saccadeOffset(4, 1, 0.3)) - 4) < 1e-9);
});

test('a nod rises and settles back to nothing', () => {
    assert.equal(nodCurve(0, 0.5), 0);
    assert.equal(nodCurve(0.5, 0.5), 0);
    assert.ok(Math.abs(nodCurve(0.25, 0.5) - 1) < 1e-12);
    assert.equal(nodCurve(-1, 0.5), 0);
});

test('nods are spaced around their mean and never overlap', () => {
    const nod = STATES.listening.nod;
    assert.equal(nodWait(nod, 0.5), nod.every);
    assert.ok(nodWait(nod, 0) >= nod.length);
    assert.ok(nodWait({ ...nod, jitter: 10 }, 0) >= nod.length);
});
