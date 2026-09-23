// what the room really heard of her, and how fast a fade reaches it, read off a real player

const test = require('node:test');
const assert = require('node:assert');

const VoiceManager = require('../classes/VoiceManager');
const { createAudioPlayer } = require('@discordjs/voice');
const { OpusEncoder } = require('@discordjs/opus');
const { BYTES_PER_MS } = require('../classes/Pcm');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const AMPLITUDE = 8000;

function tone(ms) {
    const buffer = Buffer.alloc(ms * BYTES_PER_MS);
    for (let i = 0; i < buffer.length; i += 4) {
        const value = Math.round(Math.sin((2 * Math.PI * 220 * (i / 4)) / 48000) * AMPLITUDE);
        buffer.writeInt16LE(value, i);
        buffer.writeInt16LE(value, i + 2);
    }
    return buffer;
}

function peak(pcm) {
    let top = 0;
    for (let i = 0; i < pcm.length; i += 2) top = Math.max(top, Math.abs(pcm.readInt16LE(i)));
    return top;
}

function call() {
    const client = { user: { id: 'bot' }, channels: { cache: new Map() }, on() {} };
    const mgr = new VoiceManager(client);
    mgr.link.stop();
    const reports = [];
    mgr.link.send = (message) => { reports.push(message); return true; };
    const player = createAudioPlayer({ behaviors: { noSubscriber: 'play' } });
    const data = {
        player, channelId: 'c', isSpeaking: false, speech: null,
        subscriptions: new Map(), speakers: new Map(), tick: null,
    };
    mgr.connections.set('g', data);
    mgr.watchPlayer('g', player, data);

    const heard = [];
    const decoder = new OpusEncoder(48000, 2);
    const start = Date.now();
    player.on('stateChange', (_, state) => {
        const resource = state.resource;
        if (!resource || resource.tapped) return;
        resource.tapped = true;
        const read = resource.read.bind(resource);
        resource.read = () => {
            const packet = read();
            if (packet && packet.length > 3) {
                heard.push({ at: Date.now() - start, peak: peak(decoder.decode(packet)) });
            }
            return packet;
        };
    });
    return { mgr, player, reports, heard, start };
}

const playing = (reports) => reports.filter((r) => r.type === 'playback');

test('what is reported heard is what the player has taken, not what arrived', async (t) => {
    const { mgr, player, reports, heard } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(3000));
    await sleep(700);

    const said = playing(reports).at(-1).played_ms;
    const taken = heard.length * 20;
    assert.ok(said <= taken + 100, `reported ${said}ms heard after the player took ${taken}ms`);
});

test('a stop reports how far into the sentence she really got', async (t) => {
    const { mgr, player, reports, heard } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(3000));
    await sleep(600);
    mgr.stopSpeaking(200);
    await sleep(400);

    const stopped = playing(reports).at(-1);
    assert.equal(stopped.state, 'stopped');
    const taken = heard.length * 20;
    assert.ok(stopped.played_ms < 1500, `a three second sentence cut at ${taken}ms reported ${stopped.played_ms}ms heard`);
    assert.ok(Math.abs(stopped.played_ms - taken) <= 60, `reported ${stopped.played_ms}ms, the room got ${taken}ms`);
});

test('a duck turns down the sentence already queued, not just the next one', async (t) => {
    const { mgr, player, heard, start } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(3000));
    await sleep(500);
    const duckedAt = Date.now() - start;
    mgr.duck(0.25, 20);
    await sleep(500);

    const after = heard.filter((h) => h.at >= duckedAt + 150);
    assert.ok(after.length > 5, 'nothing was played after the duck');
    const loud = after.filter((h) => h.peak > AMPLITUDE * 0.4);
    assert.equal(loud.length, 0, `${loud.length} packets played at full volume after she was ducked`);
});

test('a stop fades her out before the stream is cut', async (t) => {
    const { mgr, player, heard, start } = call();
    t.after(() => player.stop(true));

    mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(3000));
    await sleep(500);
    const stoppedAt = Date.now() - start;
    mgr.stopSpeaking(200);
    await sleep(400);

    const last = heard.filter((h) => h.at >= stoppedAt).at(-1);
    assert.ok(last, 'nothing played after the stop');
    assert.ok(last.peak < AMPLITUDE * 0.1, `the last thing heard was at ${Math.round(last.peak / AMPLITUDE * 100)}% volume`);
});
