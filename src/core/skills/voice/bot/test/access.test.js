// Who Bea hears on Discord. The whitelist used to be a wall: anyone not on it
// did not exist — no perception, no roster entry, no chance of ever becoming
// someone she knows. That contradicts the whole point of her memory.

const test = require('node:test');
const assert = require('node:assert');

const { mayReach, ACCESS_MODES } = require('../access');

test('strict mode only lets the whitelist through', () => {
    assert.equal(mayReach('strict', true), true);
    assert.equal(mayReach('strict', false), false);
});

test('boost mode lets everyone through', () => {
    assert.equal(mayReach('boost', false), true);
});

test('open mode lets everyone through', () => {
    assert.equal(mayReach('open', false), true);
});

test('an unknown mode is treated as the safe one', () => {
    assert.equal(mayReach('banana', false), false);
    assert.equal(mayReach('', false), false);
});

test('the three modes are the ones the dashboard offers', () => {
    assert.deepEqual([...ACCESS_MODES], ['strict', 'boost', 'open']);
});
