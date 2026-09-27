import { test } from 'node:test';
import assert from 'node:assert/strict';

import { emptyMouth, frameAt, startMouth } from '../src/stage/mouth.js';
import { CLOSE_AT, OPEN_AT, bob, frameKey, mouthGate } from '../src/stage/sprite.js';

const PNG = { rest: 'happy/idle', open: 'happy/talking', closed: 'happy/talking_closed', blink: 'happy/blink' };

test('the mouth runs off the page clock from the moment the envelope arrived', () => {
    const mouth = startMouth([[0.1, 0], [0.2, 0], [0.3, 0]], 10, 1000);
    assert.equal(frameAt(mouth, 999), null);
    assert.deepEqual(frameAt(mouth, 1000), [0.1, 0]);
    assert.deepEqual(frameAt(mouth, 1150), [0.2, 0]);
    assert.deepEqual(frameAt(mouth, 1299), [0.3, 0]);
    assert.equal(frameAt(mouth, 1300), null);
    assert.equal(frameAt(emptyMouth(), 0), null);
});

test('the mouth opens above one level and closes below a lower one', () => {
    assert.equal(mouthGate(false, OPEN_AT + 0.01), true);
    assert.equal(mouthGate(false, (OPEN_AT + CLOSE_AT) / 2), false, 'a shut mouth stays shut in the band');
    assert.equal(mouthGate(true, (OPEN_AT + CLOSE_AT) / 2), true, 'an open mouth stays open in the band');
    assert.equal(mouthGate(true, CLOSE_AT - 0.01), false);
});

test('talking flaps between the two talking pictures', () => {
    assert.equal(frameKey(PNG, { talking: true, open: true }), 'happy/talking');
    assert.equal(frameKey(PNG, { talking: true, open: false }), 'happy/talking_closed');
});

test('a blink only shows at rest and only if the mood has one', () => {
    assert.equal(frameKey(PNG, { talking: false, blinking: true }), 'happy/blink');
    assert.equal(frameKey(PNG, { talking: true, open: false, blinking: true }), 'happy/talking_closed');
    assert.equal(frameKey({ ...PNG, blink: null }, { talking: false, blinking: true }), 'happy/idle');
});

test('nothing published draws nothing', () => {
    assert.equal(frameKey(null, { talking: true }), null);
});

test('her voice lifts the picture and the breath never stops', () => {
    const [still] = bob(0, 0);
    const [loud] = bob(0, 1);
    assert.ok(loud > still);
    const heights = [0, 0.5, 1, 1.5, 2].map((t) => bob(t)[0]);
    assert.ok(new Set(heights.map((h) => h.toFixed(3))).size > 1);
});
