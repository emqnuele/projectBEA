// Her line runs dry in the middle: the next sentence is late off the engine, or
// the model paused. The player gives up on a stream that stops delivering and
// goes idle, and that used to end the utterance — the bot reported it done, the
// brain took it as the room having moved on and dropped the rest of the line,
// and whatever still arrived for it started over with a count from zero.
//
// These run a real AudioPlayer, with no connection to play into, on a gap of a
// fifth of a second instead of three so they finish quickly.

const test = require('node:test');
const assert = require('node:assert');

const VoiceManager = require('../classes/VoiceManager');
const { createAudioPlayer } = require('@discordjs/voice');
const { BYTES_PER_MS } = require('../classes/Pcm');

const GAP_MS = 200;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function tone(ms) {
    const buffer = Buffer.alloc(ms * BYTES_PER_MS);
    for (let i = 0; i < buffer.length; i += 2) buffer.writeInt16LE(3000, i);
    return buffer;
}

function call() {
    const client = { user: { id: 'bot' }, channels: { cache: new Map() }, on() {} };
    const mgr = new VoiceManager(client);
    mgr.link.stop();
    const reports = [];
    mgr.link.send = (message) => { reports.push(message); return true; };

    const options = VoiceManager.playerOptions(GAP_MS);
    // nobody is subscribed in a test: play anyway, as a call would
    const player = createAudioPlayer({ behaviors: { ...options.behaviors, noSubscriber: 'play' } });
    const data = {
        player, channelId: 'c', isSpeaking: false, speech: null,
        subscriptions: new Map(), speakers: new Map(), tick: null,
    };
    mgr.connections.set('g', data);
    mgr.watchPlayer('g', player, data);
    return { mgr, player, data, reports };
}

const states = (reports, id) => reports.filter((r) => r.type === 'playback' && r.utterance_id === id);

test('a line that runs dry halfway is still one utterance', async (t) => {
    const { mgr, player, reports } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(300));
    // the audio, the gap the player allows, its padding, and then some
    await sleep(300 + GAP_MS + 500);
    assert.ok(!states(reports, 'u').some((r) => r.state === 'done'),
        'running dry ended the utterance');

    mgr.playPushed({ utterance_id: 'u', seq: 1, last: false }, tone(300));
    mgr.playPushed({ utterance_id: 'u', seq: -1, last: true }, Buffer.alloc(0));
    await sleep(300 + 600);

    const seen = states(reports, 'u');
    assert.equal(seen.filter((r) => r.played_ms === 0).length, 1, 'the count started over');
    const done = seen.filter((r) => r.state === 'done');
    assert.equal(done.length, 1, 'the utterance never ended, or ended twice');
    assert.equal(done[0].played_ms, 600, 'the room heard both halves');
    assert.equal(mgr.connections.get('g').speech, null);
});

test('the end of a line that already ran dry ends it at once', async (t) => {
    const { mgr, player, reports } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    await sleep(200 + GAP_MS + 500);
    mgr.playPushed({ utterance_id: 'u', seq: -1, last: true }, Buffer.alloc(0));

    const done = states(reports, 'u').filter((r) => r.state === 'done');
    assert.equal(done.length, 1, 'nothing is left to play, so nothing would ever say it ended');
    assert.equal(done[0].played_ms, 200);
});

test('a line stopped while it had run dry is reported stopped', async (t) => {
    const { mgr, player, reports } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    await sleep(200 + GAP_MS + 500);
    mgr.stopSpeaking(20);
    // the fade, and the frames still on their way to the room behind it
    await sleep(250);

    const seen = states(reports, 'u');
    assert.equal(seen.at(-1).state, 'stopped');
    assert.equal(seen.at(-1).played_ms, 200);
});

test('turned down, she stays turned down across a gap in her line', async (t) => {
    const { mgr, player, data } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    mgr.duck(0.25, 1);
    await sleep(200 + GAP_MS + 500);
    mgr.playPushed({ utterance_id: 'u', seq: 1, last: false }, tone(200));

    assert.equal(data.speech.gain.gain, 0.25, 'the rest of the line came back at full volume');
});

test('a new line still replaces one that ran dry', async (t) => {
    const { mgr, player, reports } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'a', seq: 0, last: false }, tone(200));
    await sleep(200 + GAP_MS + 500);
    mgr.playPushed({ utterance_id: 'b', seq: 0, last: true }, tone(200));
    await sleep(200 + 600);

    assert.equal(states(reports, 'a').at(-1).state, 'stopped');
    assert.equal(states(reports, 'b').at(-1).state, 'done');
});
