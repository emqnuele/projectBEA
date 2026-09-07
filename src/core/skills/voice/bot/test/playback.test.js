// Her voice on the way to the room: the fade that makes an interruption sound
// human, and the count that tells the brain how much of a sentence was heard.
// Getting the count wrong is worse than getting it late — she would go on
// referring to half a line nobody got.

const test = require('node:test');
const assert = require('node:assert');

const { PcmGain, BYTES_PER_MS } = require('../classes/PcmGain');
const { unframe } = require('../classes/BrainLink');

// n milliseconds of full-scale 48khz stereo s16le
function tone(ms) {
    const buffer = Buffer.alloc(ms * BYTES_PER_MS);
    for (let i = 0; i < buffer.length; i += 2) buffer.writeInt16LE(20000, i);
    return buffer;
}

function through(gain, chunk) {
    return new Promise((resolve) => {
        const out = [];
        gain.on('data', (d) => out.push(d));
        gain.write(chunk);
        gain.end();
        gain.on('end', () => resolve(Buffer.concat(out)));
    });
}

test('at full volume the samples are passed through untouched', async () => {
    const gain = new PcmGain();
    const input = tone(20);
    assert.deepEqual(await through(gain, input), input);
});

test('what got through is counted in milliseconds', async () => {
    const gain = new PcmGain();
    await through(gain, tone(500));
    assert.equal(gain.playedMs, 500);
});

test('ducking turns her down without silencing her', async () => {
    const gain = new PcmGain();
    gain.rampTo(0.25, 0); // no ramp: assert the destination, not the slope
    const out = await through(gain, tone(20));
    assert.ok(Math.abs(out.readInt16LE(out.length - 2) - 5000) < 50);
});

test('a fade to silence ends at silence, not at a cliff', async () => {
    const gain = new PcmGain();
    gain.rampTo(0, 10);
    const out = await through(gain, tone(20));

    assert.ok(out.readInt16LE(0) > 19000, 'starts at full volume');
    assert.equal(out.readInt16LE(out.length - 2), 0, 'ends silent');
    // and gets there gradually: the midpoint of the ramp sits in between
    const middle = Math.floor((5 * BYTES_PER_MS) / 4) * 4;
    const half = out.readInt16LE(middle);
    assert.ok(half > 2000 && half < 18000, `ramp midpoint was ${half}`);
});

test('a chunk that splits mid-frame does not lose a sample', async () => {
    const gain = new PcmGain();
    const input = tone(10);
    const out = await new Promise((resolve) => {
        const chunks = [];
        gain.on('data', (d) => chunks.push(d));
        gain.write(input.subarray(0, 101)); // deliberately not frame-aligned
        gain.write(input.subarray(101));
        gain.end();
        gain.on('end', () => resolve(Buffer.concat(chunks)));
    });
    assert.equal(out.length % 4, 0);
    assert.equal(out.length, input.length);
});

test('progress is reported while she is still talking', async () => {
    // the player pulls this stream in frames, which is what makes the count
    // track what was heard instead of what was queued
    const seen = [];
    const gain = new PcmGain((ms) => seen.push(ms));
    const out = [];
    gain.on('data', (d) => out.push(d));
    for (let i = 0; i < 10; i += 1) gain.write(tone(100));
    gain.end();
    await new Promise((resolve) => gain.on('end', resolve));

    assert.ok(seen.length >= 3, `only ${seen.length} progress reports`);
    assert.ok(seen[0] <= 300);
    assert.equal(gain.playedMs, 1000);
});

test('a pushed audio frame is read back as its header and its samples', () => {
    const header = Buffer.from(JSON.stringify({ type: 'play', utterance_id: 'u1', last: true }));
    const size = Buffer.alloc(4);
    size.writeUInt32BE(header.length, 0);
    const payload = tone(5);

    const frame = unframe(Buffer.concat([size, header, payload]));
    assert.equal(frame.header.utterance_id, 'u1');
    assert.deepEqual(frame.payload, payload);
});

test('a frame that arrives short is refused rather than half-read', () => {
    assert.equal(unframe(Buffer.from([0, 0, 0, 10, 1, 2])), null);
});
