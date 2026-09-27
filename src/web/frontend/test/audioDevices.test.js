import { test } from 'node:test';
import assert from 'node:assert/strict';

import { chosenDevice, deviceChoices, deviceFor, latencyNote } from '../src/lib/audioDevices.js';

const DEVICES = [
    { id: 0, name: 'MSI G242', channels: 2, latency_ms: 15, default: false },
    { id: 2, name: 'CMF Buds 2', channels: 2, latency_ms: 185, default: true },
    { id: 5, name: 'MacBook Air Speakers', channels: 2, latency_ms: 15, default: false },
];

test('a device listed once per audio api is offered once, the default entry kept', () => {
    const doubled = [{ id: 1, name: 'Speakers', default: false }, { id: 4, name: 'Speakers', default: true }];
    assert.deepEqual(deviceChoices(doubled).map((d) => d.id), [4]);
});

test('the stored name is what the picker shows', () => {
    assert.equal(chosenDevice({ audio_device: 'MacBook Air Speakers', audio_device_id: 0 }, DEVICES), 'MacBook Air Speakers');
});

test('an old position is shown as the device it points at today', () => {
    assert.equal(chosenDevice({ audio_device: '', audio_device_id: 2 }, DEVICES), 'CMF Buds 2');
});

test('nothing stored, or a position with nothing behind it, is the system default', () => {
    assert.equal(chosenDevice({}, DEVICES), '');
    assert.equal(chosenDevice({ audio_device_id: 9 }, DEVICES), '');
});

test('the system default lands on the device the system marks as default', () => {
    assert.equal(deviceFor('', DEVICES).name, 'CMF Buds 2');
    assert.equal(deviceFor('Unplugged', DEVICES), null);
});

test('only a slow output gets a note about its latency', () => {
    assert.match(latencyNote(DEVICES[1]), /185 ms/);
    assert.equal(latencyNote(DEVICES[2]), null);
    assert.equal(latencyNote(null), null);
});
