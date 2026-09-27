import { test } from 'node:test';
import assert from 'node:assert/strict';

import { latestOnly } from '../src/stage/latest.js';

function deferred() {
    let resolve;
    const promise = new Promise((r) => { resolve = r; });
    return { promise, resolve };
}

test('a model asked for earlier that loads later is thrown away, not put on stage', async () => {
    const pending = { a: deferred(), b: deferred() };
    const discarded = [];
    const load = latestOnly((name) => pending[name].promise, (result) => discarded.push(result));

    const first = load('a');
    const second = load('b');
    pending.b.resolve('rig b');
    pending.a.resolve('rig a');

    assert.equal(await second, 'rig b');
    assert.equal(await first, null);
    assert.deepEqual(discarded, ['rig a']);
});

test('a single load is kept', async () => {
    const load = latestOnly(async (name) => `rig ${name}`, () => assert.fail('nothing to discard'));
    assert.equal(await load('a'), 'rig a');
});

test('a failed load still fails for its caller', async () => {
    const load = latestOnly(async () => { throw new Error('bad file'); }, () => {});
    await assert.rejects(load('a'), /bad file/);
});
