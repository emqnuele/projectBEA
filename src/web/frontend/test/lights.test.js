import { test } from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_LIGHTS, LIGHT_PRESETS, lightPreset } from '../src/stage/lights.js';

test('the default is the rig she has always been lit by', () => {
    assert.equal(DEFAULT_LIGHTS, 'flat');
    assert.deepEqual(LIGHT_PRESETS.flat.lights, [
        { type: 'directional', color: '#ffffff', intensity: 2.0, position: [1, 2, 1.5] },
        { type: 'ambient', color: '#ffffff', intensity: 1.1 },
    ]);
    assert.equal(LIGHT_PRESETS.flat.rim, null);
});

test('an unknown preset falls back instead of leaving her in the dark', () => {
    assert.equal(lightPreset('disco'), LIGHT_PRESETS.flat);
    assert.equal(lightPreset(undefined), LIGHT_PRESETS.flat);
});

test('every preset lights her from the camera side and never from nothing', () => {
    for (const [name, preset] of Object.entries(LIGHT_PRESETS)) {
        const keys = preset.lights.filter((l) => l.type === 'directional');
        assert.ok(keys.some((l) => l.position[2] > 0), `${name} has no light in front of her`);
        for (const light of preset.lights) {
            assert.ok(light.intensity > 0, name);
            assert.match(light.color, /^#[0-9a-f]{6}$/);
            if (light.type === 'directional') assert.equal(light.position.length, 3);
        }
    }
});

test('a rim, where there is one, is a colour, a power and a lift', () => {
    const { rim } = LIGHT_PRESETS.studio;
    assert.match(rim.color, /^#[0-9a-f]{6}$/);
    assert.ok(rim.power > 0 && rim.lift >= 0);
});
