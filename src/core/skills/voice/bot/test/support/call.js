// The bot's half of a call with no discord in it, for the brain's end-to-end
// test: the real BrainLink and VoiceManager, and a real AudioPlayer that plays
// to nobody. Reads BRAIN_API_URL and API_TOKEN like the bot does.
//
//     node call.js <player gap in ms>

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

// in the call before the link opens, so the first thing the brain hears is that
const announce = VoiceManager.prototype.announceCall;
VoiceManager.prototype.announceCall = function () {
    if (!this.connections.has('g')) {
        this.connections.set('g', data);
        this.watchPlayer('g', player, data);
    }
    return announce.call(this);
};
new VoiceManager(client);

// the brain ends the test; this only makes sure an orphan does not linger
setTimeout(() => process.exit(0), 30000).unref();
process.on('SIGTERM', () => process.exit(0));
