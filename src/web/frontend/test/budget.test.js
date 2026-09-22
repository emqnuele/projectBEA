import assert from 'node:assert/strict';
import test from 'node:test';
import { derivedTokens, windowShape } from '../src/lib/budget.js';

const DERIVES = [
    { key: 'handoff_trigger_tokens', label: 'hands off at', ratio: 0.8 },
    { key: 'handoff_target_tokens', label: 'rests near', ratio: 1 / 3 },
    { key: 'hot_tokens', label: 'keeps verbatim', ratio: 0.2 },
];

const tokensAt = (ceiling, values = {}) =>
    Object.fromEntries(windowShape(ceiling, DERIVES, values).map((d) => [d.key, d.tokens]));

// golden values, taken from token_budget.budget_for in the engine: the number
// under the slider has to be the number that comes back after saving
test('the derived shape matches what the engine works out', () => {
    assert.deepEqual(tokensAt(150_000), {
        handoff_trigger_tokens: 120_000,
        handoff_target_tokens: 50_000,
        hot_tokens: 30_000,
    });
    assert.deepEqual(tokensAt(300_000), {
        handoff_trigger_tokens: 240_000,
        handoff_target_tokens: 100_000,
        hot_tokens: 60_000,
    });
    assert.deepEqual(tokensAt(500_000), {
        handoff_trigger_tokens: 400_000,
        handoff_target_tokens: 167_000,
        hot_tokens: 100_000,
    });
});

test('every slider position derives whole thousands, rising with the ceiling', () => {
    let previous = 0;
    for (let ceiling = 150_000; ceiling <= 500_000; ceiling += 10_000) {
        const trigger = derivedTokens(ceiling, 0.8);
        assert.equal(trigger % 1000, 0, `${ceiling} derives a ragged ${trigger}`);
        assert.ok(trigger > previous, `${ceiling} did not raise the trigger`);
        previous = trigger;
    }
});

test('a pinned value wins over the ceiling and says so', () => {
    const shape = windowShape(500_000, DERIVES, { handoff_trigger_tokens: 90_000 });
    const trigger = shape.find((d) => d.key === 'handoff_trigger_tokens');
    assert.equal(trigger.tokens, 90_000);
    assert.equal(trigger.pinned, true);
    // the rest still follows the ceiling
    assert.equal(shape.find((d) => d.key === 'hot_tokens').pinned, false);
});

test('zero means follow, not a window of nothing', () => {
    const shape = windowShape(200_000, DERIVES, { hot_tokens: 0, handoff_target_tokens: null });
    assert.equal(shape.find((d) => d.key === 'hot_tokens').tokens, 40_000);
    assert.equal(shape.find((d) => d.key === 'handoff_target_tokens').tokens, 67_000);
});
