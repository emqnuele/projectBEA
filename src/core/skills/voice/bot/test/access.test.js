// Who Bea hears on Discord. The whitelist used to be a wall: anyone not on it
// did not exist — no perception, no roster entry, no chance of ever becoming
// someone she knows. That contradicts the whole point of her memory.

const test = require('node:test');
const assert = require('node:assert');

const { mayReach, checkCommandAccess, ACCESS_MODES } = require('../access');

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

// --- who may run a `!command` ---------------------------------------------

// the owner is the admin: everything, whitelist or not
test('the owner runs voice commands without the whitelist', () => {
    assert.deepEqual(
        checkCommandAccess({ category: 'voice', isOwner: true, whitelisted: false }),
        { allowed: true, reason: 'owner' });
});

test('the owner runs admin commands', () => {
    assert.deepEqual(
        checkCommandAccess({ category: 'admin', isOwner: true, whitelisted: false }),
        { allowed: true, reason: 'owner' });
});

test('a whitelisted user runs ordinary commands but not admin ones', () => {
    assert.deepEqual(
        checkCommandAccess({ category: 'voice', isOwner: false, whitelisted: true }),
        { allowed: true, reason: 'whitelisted' });
    assert.deepEqual(
        checkCommandAccess({ category: 'admin', isOwner: false, whitelisted: true }),
        { allowed: false, reason: 'owner-only' });
});

test('a stranger runs nothing, with the reason named', () => {
    assert.deepEqual(
        checkCommandAccess({ category: 'voice', isOwner: false, whitelisted: false }),
        { allowed: false, reason: 'not-whitelisted' });
    assert.deepEqual(
        checkCommandAccess({ category: 'admin', isOwner: false, whitelisted: false }),
        { allowed: false, reason: 'owner-only' });
});
