/**
 * What the brain is told about somebody talking, as it happens: that they
 * started, that a turn of theirs is on its way to be transcribed, and that they
 * stopped. A turn only reaches the brain once it is over and transcribed; this
 * is what lets her wait for the rest of a sentence instead of answering half.
 */

const test = require('node:test');
const assert = require('node:assert');
const { PassThrough } = require('stream');
const { OpusEncoder } = require('@discordjs/opus');

const VoiceManager = require('../classes/VoiceManager');
const { HANGOVER_MS } = require('../classes/VoiceActivity');
const { BYTES_PER_MS } = require('../classes/Pcm');

const RATE = 48000;

function voice(ms) {
    const buffer = Buffer.alloc(Math.round(ms * BYTES_PER_MS));
    for (let i = 0; i < buffer.length; i += 4) {
        const t = (i / 4) / RATE;
        let value = 0;
        for (let h = 1; h <= 18; h += 1) value += (1 / h) * Math.sin(2 * Math.PI * 140 * h * t);
        const sample = Math.round(3000 * value);
        buffer.writeInt16LE(sample, i);
        buffer.writeInt16LE(sample, i + 2);
    }
    return buffer;
}

/** A manager with no discord and no brain, and one person in the call. */
function call() {
    const client = {
        user: { id: 'bot' },
        channels: { cache: new Map() },
        guilds: { fetch: async () => { throw new Error('offline'); } },
        on() {},
    };
    const mgr = new VoiceManager(client);
    mgr.link.stop();
    const told = [];
    mgr.link.send = (message) => { told.push(message); return true; };
    // the turn itself goes nowhere: what is under test is what the brain is told
    mgr.speechForm = () => ({ getHeaders: () => ({}) });
    mgr.apiBaseUrl = 'http://127.0.0.1:9';

    const packets = new PassThrough({ objectMode: true });
    mgr.connections.set('g', {
        connection: { receiver: { subscribe: () => packets } },
        isSpeaking: false, speech: null, subscriptions: new Map(), speakers: new Map(), tick: null,
    });
    mgr.createStream('g', 'u');
    const encoder = new OpusEncoder(RATE, 2);
    const say = (audio) => {
        for (let at = 0; at + 3840 <= audio.length; at += 3840) {
            packets.write(encoder.encode(audio.subarray(at, at + 3840)));
        }
    };
    const hearing = () => told.filter((m) => m.type === 'hearing').map((m) => `${m.state}:${m.user_id}`);
    return { mgr, say, hearing, packets };
}

/** Nothing arriving, with the sweep looking, until the turn has had time to end. */
async function silence(mgr, ms) {
    const until = Date.now() + ms;
    while (Date.now() < until) {
        mgr.sweep('g');
        await new Promise((resolve) => setTimeout(resolve, 20));
    }
}

test('somebody talking is told as it starts, then as their turn leaves, then as they stop', async () => {
    const { mgr, say, hearing, packets } = call();

    say(voice(800));
    await new Promise((resolve) => setImmediate(resolve));
    await silence(mgr, 60);
    assert.deepStrictEqual(hearing(), ['start:u'], 'the brain was not told they started');

    await silence(mgr, HANGOVER_MS + 300);
    assert.deepStrictEqual(hearing(), ['start:u', 'sent:u', 'end:u']);
    packets.end();
});

test('a sound that was never words ends without a turn on its way', async () => {
    const { mgr, say, hearing, packets } = call();

    // long enough to be believed as somebody starting, too short to be speech
    say(voice(140));
    await silence(mgr, HANGOVER_MS + 300);
    assert.deepStrictEqual(hearing(), ['start:u', 'end:u']);
    packets.end();
});
