// A disconnect used to drop the call state without destroying the connection:
// a channel move or a network blip left her sitting in the call and deaf,
// while the brain thought she had left. These pin the official pattern — wait
// out the transient, destroy the dead — plus the move/kick handling, against
// fakes instead of a real call.

const test = require('node:test');
const assert = require('node:assert');
const { EventEmitter } = require('node:events');

const VoiceManager = require('../classes/VoiceManager');
const { VoiceConnectionStatus, VoiceConnectionDisconnectReason } = require('@discordjs/voice');

function fakeClient() {
    return {
        user: { id: 'bot-id' },
        channels: { cache: new Map() },
        guilds: { fetch: async () => ({ members: { fetch: async () => ({ displayName: 'ema' }) } }) },
        _handlers: {},
        on(event, fn) { this._handlers[event] = fn; },
    };
}

function managerWithConnection({ state = {}, channelId = 'chan-1' } = {}) {
    const client = fakeClient();
    const mgr = new VoiceManager(client);
    // keep the constructor's link quiet: no brain on the other end here
    mgr.link.stop();
    mgr.announced = [];
    mgr.link.send = (msg) => { mgr.announced.push(msg); return true; };

    const connection = new EventEmitter();
    connection.state = state;
    connection.destroyed = false;
    connection.destroy = function () { this.destroyed = true; };
    connection.receiver = { speaking: new EventEmitter() };

    mgr.connections.set('guild-1', {
        connection,
        player: { stop() {} },
        channelId,
        isSpeaking: false,
        speech: null,
        subscriptions: new Map(),
        speakers: new Map(),
        tick: null,
    });
    return { mgr, connection };
}

test('a transient blip keeps the call: no destroy, no cleanup', async () => {
    const { mgr, connection } = managerWithConnection({ state: { status: VoiceConnectionStatus.Disconnected } });
    const recovering = async () => ({ status: VoiceConnectionStatus.Signalling });

    await mgr.handleDisconnect('guild-1', recovering);

    assert.equal(connection.destroyed, false);
    assert.ok(mgr.connections.has('guild-1'), 'the call state survives a blip');
});

test('a connection that stays down is destroyed and reported left', async () => {
    const { mgr, connection } = managerWithConnection({ state: { status: VoiceConnectionStatus.Disconnected } });
    const stuck = async () => { throw new Error('timed out'); };

    await mgr.handleDisconnect('guild-1', stuck);

    assert.equal(connection.destroyed, true);
    assert.ok(!mgr.connections.has('guild-1'));
    assert.deepEqual(mgr.announced.at(-1), { type: 'left' });
});

test('being kicked destroys immediately without waiting', async () => {
    const { mgr, connection } = managerWithConnection({
        state: {
            status: VoiceConnectionStatus.Disconnected,
            reason: VoiceConnectionDisconnectReason.WebSocketClose,
            closeCode: 4014,
        },
    });
    let waited = false;
    const never = async () => { waited = true; throw new Error('should not wait'); };

    await mgr.handleDisconnect('guild-1', never);

    assert.equal(waited, false);
    assert.equal(connection.destroyed, true);
    assert.ok(!mgr.connections.has('guild-1'));
});

test('a manual disconnect just cleans up', async () => {
    const { mgr, connection } = managerWithConnection({
        state: {
            status: VoiceConnectionStatus.Disconnected,
            reason: VoiceConnectionDisconnectReason.Manual,
        },
    });
    let waited = false;
    const never = async () => { waited = true; return {}; };

    await mgr.handleDisconnect('guild-1', never);

    assert.equal(waited, false);
    assert.equal(connection.destroyed, false);
    assert.ok(!mgr.connections.has('guild-1'));
});

test('being dragged to another channel moves the tracked channel', () => {
    const { mgr } = managerWithConnection({ channelId: 'chan-1' });

    mgr.handleVoiceStateUpdate(
        { guild: { id: 'guild-1' }, member: { id: 'bot-id' }, channelId: 'chan-1' },
        { guild: { id: 'guild-1' }, member: { id: 'bot-id' }, channelId: 'chan-2' },
    );

    assert.equal(mgr.connections.get('guild-1').channelId, 'chan-2');
    assert.equal(mgr.announced.at(-1).type, 'joined');
    assert.equal(mgr.announced.at(-1).channel_id, 'chan-2');
});

test('being kicked out of the channel destroys and reports left', () => {
    const { mgr, connection } = managerWithConnection({ channelId: 'chan-1' });

    mgr.handleVoiceStateUpdate(
        { guild: { id: 'guild-1' }, member: { id: 'bot-id' }, channelId: 'chan-1' },
        { guild: { id: 'guild-1' }, member: { id: 'bot-id' }, channelId: null },
    );

    assert.equal(connection.destroyed, true);
    assert.ok(!mgr.connections.has('guild-1'));
    assert.deepEqual(mgr.announced.at(-1), { type: 'left' });
});

test('someone else moving only refreshes the room, never the channel', () => {
    const { mgr, connection } = managerWithConnection({ channelId: 'chan-1' });

    mgr.handleVoiceStateUpdate(
        { guild: { id: 'guild-1' }, member: { id: 'someone' }, channelId: null },
        { guild: { id: 'guild-1' }, member: { id: 'someone' }, channelId: 'chan-1' },
    );

    assert.equal(connection.destroyed, false);
    assert.equal(mgr.connections.get('guild-1').channelId, 'chan-1');
});
