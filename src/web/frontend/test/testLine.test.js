import { test } from 'node:test';
import assert from 'node:assert/strict';

import { testEnvelope } from '../src/lib/testLine.js';

test('the test line lasts what it was asked to, at the rate asked', () => {
    assert.equal(testEnvelope(3, 30).length, 90);
    assert.equal(testEnvelope(2, 60).length, 120);
});

test('every frame is an opening and a vowel, both between 0 and 1', () => {
    for (const [open, shape] of testEnvelope(4, 30)) {
        assert.ok(open >= 0 && open <= 1);
        assert.ok(shape >= 0 && shape <= 1);
    }
});

test('it opens and closes like speech rather than holding still', () => {
    const frames = testEnvelope(3, 30);
    assert.ok(frames.some(([open]) => open > 0.4));
    assert.ok(frames.filter(([open]) => open === 0).length > 3, 'no pause between words');
});

test('the same seed is the same line', () => {
    assert.deepEqual(testEnvelope(3, 30, 11), testEnvelope(3, 30, 11));
    assert.notDeepEqual(testEnvelope(3, 30, 11), testEnvelope(3, 30, 12));
});
