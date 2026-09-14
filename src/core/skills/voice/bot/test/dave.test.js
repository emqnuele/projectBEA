// Joining a voice channel since discord made end-to-end encryption mandatory:
// without dave the bot shows up in the channel but stays deaf and mute, which
// is exactly how a working call looks from the outside. These tests pin the
// join options so the encryption cannot be dropped silently again.

const test = require('node:test');
const assert = require('node:assert');

const { buildJoinOptions } = require('../classes/VoiceManager');

test('the join asks for dave encryption', () => {
    const options = buildJoinOptions('guild-1', 'channel-2', 'adapter');
    assert.equal(options.daveEncryption, true);
});

test('the join still names the channel, guild and adapter', () => {
    const options = buildJoinOptions('guild-1', 'channel-2', 'adapter');
    assert.equal(options.guildId, 'guild-1');
    assert.equal(options.channelId, 'channel-2');
    assert.equal(options.adapterCreator, 'adapter');
    assert.equal(options.selfDeaf, false);
    assert.equal(options.selfMute, false);
});

test('the dave library the voice stack negotiates through is installed', () => {
    const bot = require('../package.json');
    assert.ok(bot.dependencies['@snazzah/davey'], 'davey is missing from dependencies');
    assert.match(bot.dependencies['@discordjs/voice'], /0\.19/);
});
