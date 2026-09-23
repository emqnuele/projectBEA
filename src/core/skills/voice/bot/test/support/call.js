// the bot's half of a call with no discord in it, for tests/test_voice_call_e2e.py

const VoiceManager = require('../../classes/VoiceManager');
const { createAudioPlayer } = require('@discordjs/voice');

const gapMs = Number(process.argv[2] || 3000);
const client = { user: { id: 'bot' }, channels: { cache: new Map() }, on() {} };
const player = createAudioPlayer({
    behaviors: { ...VoiceManager.playerOptions(gapMs).behaviors, noSubscriber: 'play' },
});
const data = {
    player, channelId: 'call', isSpeaking: false, speech: null,
    subscriptions: new Map(), speakers: new Map(), tick: null,
};

// joined before the link opens, so the brain's first message is that she is in a call
const announce = VoiceManager.prototype.announceCall;
VoiceManager.prototype.announceCall = function () {
    if (!this.connections.has('g')) {
        this.connections.set('g', data);
        this.watchPlayer('g', player, data);
    }
    return announce.call(this);
};
new VoiceManager(client);

// only so an orphaned process does not linger
setTimeout(() => process.exit(0), 30000).unref();
process.on('SIGTERM', () => process.exit(0));
