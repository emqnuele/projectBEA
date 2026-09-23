// a line that runs dry mid-way, on a real player with a fifth of a second of patience

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

function call(gapMs = GAP_MS) {
    const client = { user: { id: 'bot' }, channels: { cache: new Map() }, on() {} };
    const mgr = new VoiceManager(client);
    mgr.link.stop();
    const reports = [];
    mgr.link.send = (message) => { reports.push(message); return true; };

    const options = VoiceManager.playerOptions(gapMs);
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
    // the fade plus the frames still on their way to the room
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

test('dropping what has not started yet still ends a line that ran dry', async (t) => {
    const { mgr, player, reports } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    await sleep(200 + GAP_MS + 500);
    mgr.cancelPending();

    const done = states(reports, 'u').filter((r) => r.state === 'done');
    assert.equal(done.length, 1, 'the utterance was left open with nothing coming');
});

test('dropping what has not started yet lets what is playing finish, then ends it', async (t) => {
    const { mgr, player, reports } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(300));
    await sleep(100);
    mgr.cancelPending();
    await sleep(300 + 500);

    const done = states(reports, 'u').filter((r) => r.state === 'done');
    assert.equal(done.length, 1, 'the utterance never ended');
});

test('a resumed line closes the stream it left behind', async (t) => {
    const { mgr, player, data } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    const abandoned = data.speech.source;
    await sleep(200 + GAP_MS + 500);

    mgr.playPushed({ utterance_id: 'u', seq: 1, last: false }, tone(200));

    assert.notEqual(data.speech.source, abandoned, 'the line did not resume on a fresh stream');
    assert.ok(abandoned.writableEnded || abandoned.destroyed,
        'the stream the player gave up on was left open');
});

test('a line the player is padding with silence is not her speaking', async (t) => {
    const { mgr, player, data } = call(1500);
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    await sleep(120);
    assert.equal(mgr.audible(data, Date.now()), true, 'her own voice did not count as speaking');

    // the line ran dry and the player is filling the hole with silence. The
    // sweep asks once a frame in a call; do the same, and the room hearing
    // nothing of her must stop counting as her speaking
    let last = true;
    for (let i = 0; i < 40; i += 1) {
        await sleep(20);
        last = mgr.audible(data, Date.now());
    }
    assert.equal(last, false,
        'silence the player was padding with still counted as her voice');
});

test('a resume is counted and sent with the playback report', async (t) => {
    const { mgr, player, reports } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    await sleep(200 + GAP_MS + 500);
    mgr.playPushed({ utterance_id: 'u', seq: 1, last: false }, tone(200));
    mgr.playPushed({ utterance_id: 'u', seq: -1, last: true }, Buffer.alloc(0));
    await sleep(200 + 600);

    const last = states(reports, 'u').filter((r) => r.state === 'done').at(-1);
    assert.equal(last.resumed, 1, 'the report does not say the line was resumed');
});
