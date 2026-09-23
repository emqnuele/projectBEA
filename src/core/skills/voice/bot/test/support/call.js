// the bot's half of a call with no discord in it, for tests/test_voice_call_e2e.py

const { PassThrough } = require('stream');
const VoiceManager = require('../../classes/VoiceManager');
const { createAudioPlayer } = require('@discordjs/voice');
const { OpusEncoder } = require('@discordjs/opus');
const { BYTES_PER_MS } = require('../../classes/Pcm');

const gapMs = Number(process.argv[2] || 3000);
// what somebody in the call says, as "talk ms, pause ms, talk ms, ...", or nothing
const script = (process.argv[3] || '').split(',').filter(Boolean).map(Number);

const client = {
    user: { id: 'bot' },
    channels: { cache: new Map() },
    guilds: { fetch: async () => { throw new Error('no discord here'); } },
    on() {},
};
const player = createAudioPlayer({
    behaviors: { ...VoiceManager.playerOptions(gapMs).behaviors, noSubscriber: 'play' },
});
// the person, as a receiver: opus packets in, exactly as discord hands them over
const packets = new PassThrough({ objectMode: true });
const data = {
    player, channelId: 'call', isSpeaking: false, speech: null,
    subscriptions: new Map(), speakers: new Map(), tick: null,
    connection: { receiver: { subscribe: () => packets } },
};

// joined before the link opens, so the brain's first message is that she is in a call
const announce = VoiceManager.prototype.announceCall;
let spoken = false;
VoiceManager.prototype.announceCall = function () {
    if (!this.connections.has('g')) {
        this.connections.set('g', data);
        this.watchPlayer('g', player, data);
    }
    if (script.length && !spoken && this.link.open) {
        spoken = true;
        talk(this);
    }
    return announce.call(this);
};
new VoiceManager(client);

/** A voice, twenty milliseconds at a time and in real time, the way a client sends it. */
function talk(mgr) {
    mgr.createStream('g', 'u');
    data.tick = setInterval(() => mgr.sweep('g'), 20);
    const encoder = new OpusEncoder(48000, 2);
    const frame = Math.round(20 * BYTES_PER_MS);
    let t = 0;
    const steps = [];
    script.forEach((ms, i) => {
        for (let at = 0; at < ms; at += 20) steps.push(i % 2 === 0);
    });
    let n = 0;
    const clock = setInterval(() => {
        if (n >= steps.length) {
            clearInterval(clock);
            return;
        }
        if (steps[n]) {
            const pcm = Buffer.alloc(frame);
            for (let i = 0; i < pcm.length; i += 4) {
                const s = (t + i / 4) / 48000;
                let value = 0;
                for (let h = 1; h <= 18; h += 1) value += Math.sin(2 * Math.PI * 140 * h * s) / h;
                const sample = Math.round(3000 * value);
                pcm.writeInt16LE(sample, i);
                pcm.writeInt16LE(sample, i + 2);
            }
            packets.write(encoder.encode(pcm));
        }
        t += frame / 4;
        n += 1;
    }, 20);
}

// only so an orphaned process does not linger
setTimeout(() => process.exit(0), 30000).unref();
process.on('SIGTERM', () => process.exit(0));
