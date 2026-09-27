import { test } from 'node:test';
import assert from 'node:assert/strict';

import { RESYNC_MS, addSegment, emptyMouth, frameAt, startMouth, syncMouth } from '../src/stage/mouth.js';

const A = [[0.1, 0], [0.2, 0], [0.3, 0]];
const B = [[0.7, 1], [0.8, 1]];

test('a call line waits silent for the room before the mouth moves', () => {
    const mouth = addSegment(emptyMouth(), 'u1', A, 10, 0);
    assert.equal(frameAt(mouth, 0), null);
    assert.equal(frameAt(mouth, 10_000), null);
});

test('pieces are placed at their offset from the moment the room hears the line', () => {
    let mouth = addSegment(emptyMouth(), 'u1', A, 10, 0);
    mouth = syncMouth(mouth, 'u1', 0, 1000);
    mouth = addSegment(mouth, 'u1', B, 10, 300);
    assert.deepEqual(frameAt(mouth, 1000), A[0]);
    assert.deepEqual(frameAt(mouth, 1250), A[2]);
    assert.deepEqual(frameAt(mouth, 1300), B[0]);
    assert.deepEqual(frameAt(mouth, 1450), B[1]);
    assert.equal(frameAt(mouth, 1500), null);
});

test('a report that the room is further along moves the mouth there', () => {
    let mouth = addSegment(emptyMouth(), 'u1', [...A, ...A, ...A], 10, 0);
    mouth = syncMouth(mouth, 'u1', 0, 1000);
    // the player ran dry for 200 ms: at page time 1600 the room has heard only 400
    mouth = syncMouth(mouth, 'u1', 400, 1600);
    assert.equal(mouth.startedAt, 1200);
    assert.deepEqual(frameAt(mouth, 1600), [...A, ...A, ...A][4]);
});

test('jitter smaller than the resync step leaves the clock alone', () => {
    let mouth = syncMouth(addSegment(emptyMouth(), 'u1', A, 10, 0), 'u1', 0, 1000);
    const moved = syncMouth(mouth, 'u1', 250, 1250 + RESYNC_MS - 1);
    assert.equal(moved.startedAt, 1000);
});

test('a report can arrive before the first piece and still place it', () => {
    let mouth = syncMouth(emptyMouth(), 'u1', 0, 1000);
    mouth = addSegment(mouth, 'u1', A, 10, 0);
    assert.deepEqual(frameAt(mouth, 1100), A[1]);
});

test('a new line throws the old one away', () => {
    let mouth = syncMouth(addSegment(emptyMouth(), 'u1', A, 10, 0), 'u1', 0, 1000);
    mouth = addSegment(mouth, 'u2', B, 10, 0);
    assert.equal(mouth.id, 'u2');
    assert.equal(frameAt(mouth, 1000), null, 'the new line waits for its own report');
});

test('a line played here is one segment starting when it arrives', () => {
    const mouth = startMouth(A, 10, 500);
    assert.deepEqual(frameAt(mouth, 500), A[0]);
    assert.deepEqual(frameAt(mouth, 699), A[1]);
    assert.equal(frameAt(mouth, 800), null);
    assert.equal(frameAt(emptyMouth(), 0), null);
});
