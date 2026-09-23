// A line the bot holds ahead of the room. The bot cannot pause a socket it does
// not own, so the bytes are buffered rather than lost — but a line queued
// seconds ahead means the brain is sending faster than the player is playing,
// and that is worth saying out loud instead of hiding in a stream's buffer.

const test = require('node:test');
const assert = require('node:assert');

const VoiceManager = require('../classes/VoiceManager');
const { createAudioPlayer } = require('@discordjs/voice');
const { BYTES_PER_MS } = require('../classes/Pcm');

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

    const player = createAudioPlayer({ behaviors: { noSubscriber: 'play' } });
    const data = {
        player, channelId: 'c', isSpeaking: false, speech: null,
        subscriptions: new Map(), speakers: new Map(), tick: null,
    };
    mgr.connections.set('g', data);
    mgr.watchPlayer('g', player, data);
    return { mgr, player, data, reports };
}

test('a line held seconds ahead of the room is named rather than buffered in silence', (t) => {
    const { mgr, player } = call();
    t.after(() => player.stop(true));

    const warnings = [];
    const original = console.warn;
    console.warn = (...args) => warnings.push(args.join(' '));
    try {
        // one burst far longer than the player can have consumed synchronously
        mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(6000));
    } finally {
        console.warn = original;
    }

    assert.ok(warnings.length, 'nothing was said about a six second queue');
    assert.ok(warnings[0].includes('queued ahead'), `unexpected warning: ${warnings[0]}`);
    assert.ok(warnings[0].includes('u'), 'the warning does not name the utterance');
});

test('a line that is keeping up is not worth a warning', (t) => {
    const { mgr, player } = call();
    t.after(() => player.stop(true));

    const warnings = [];
    const original = console.warn;
    console.warn = (...args) => warnings.push(args.join(' '));
    try {
        mgr.playPushed({ utterance_id: 'u', seq: 0, last: false }, tone(200));
    } finally {
        console.warn = original;
    }

    assert.deepEqual(warnings, [], 'a two-hundred-millisecond piece raised a warning');
});