// The player's own numbers, pinned. "How much did the room hear" is read off
// `@discordjs/voice`: the frames the resource actually handed the player, with
// its silence-padding frames excluded. Those semantics are what makes a cut-off
// honest, and a library bump that changes them would quietly turn every stop
// into a full sentence. This is the test that fails when that happens, so the
// next person reads the numbers before trusting them.

const test = require('node:test');
const assert = require('node:assert');
const { once } = require('node:events');
const { Readable } = require('node:stream');

const { createAudioResource, StreamType } = require('@discordjs/voice');

function resource(packets) {
    return createAudioResource(Readable.from(packets), {
        inputType: StreamType.Opus,
        silencePaddingFrames: 5,
    });
}

test('a real frame counts as heard, and the padding sentinel starts unset', () => {
    const packet = Buffer.from([1, 2, 3, 4]);
    const audio = resource([packet]);

    assert.equal(audio.playbackDuration, 0, 'nothing has been heard yet');
    assert.equal(audio.silenceRemaining, -1, 'padding must not have started');

    assert.equal(audio.read(), packet);
    assert.equal(audio.playbackDuration, 20, 'one frame is twenty milliseconds of heard audio');
    assert.equal(audio.silenceRemaining, -1, 'a live stream is not in its padding');
});

test('silence padding is played, never counted as heard', async () => {
    const packet = Buffer.from([1, 2, 3, 4]);
    const source = Readable.from([packet]);
    const audio = createAudioResource(source, {
        inputType: StreamType.Opus,
        silencePaddingFrames: 5,
    });
    const ended = once(source, 'end');

    assert.equal(audio.read(), packet);
    // reading past the last frame is what lets the stream end: only then can
    // the resource know it is out of live audio and move to its padding
    assert.equal(audio.read(), null);
    await ended;

    // the stream can no longer supply a frame: the resource enters its padding,
    // which is the signal canTakeMore uses to say "this one is over"
    assert.equal(audio.readable, true, 'padding is still readable');
    assert.equal(audio.silenceRemaining, 5, 'all five padding frames are pending');
    assert.equal(audio.ended, true);

    const heard = audio.playbackDuration;
    for (let i = 0; i < 5; i += 1) {
        assert.ok(audio.read(), `padding frame ${i} was not played`);
        assert.equal(audio.playbackDuration, heard, 'padding advanced the heard count');
    }
    assert.equal(audio.silenceRemaining, 0);
    assert.equal(audio.read(), null, 'the resource is spent');
});