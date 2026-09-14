// The command door: who gets in, and — the fix — that a refusal answers
// instead of going silent. A lockout nobody can see is a lockout nobody
// can fix, which is exactly where the owner ended up.

process.env.ADMIN_ID = 'owner-1';

const test = require('node:test');
const assert = require('node:assert');

const config = require('../config');
const whitelist = require('../whitelist');
const { handleCommand } = require('../handlers/messages');

const OWNER = 'owner-1';
const LISTED = 'listed-2';
const STRANGER = 'stranger-3';

function message(authorId, command) {
    const replies = [];
    return {
        msg: {
            author: { id: authorId },
            content: `!${command}`,
            reply: async (payload) => { replies.push(payload); return null; },
        },
        replies,
    };
}

function client(executed) {
    const commands = new Map();
    for (const [name, category] of [['join', 'voice'], ['leave', 'voice'], ['hello', 'general'], ['wl', 'admin']]) {
        commands.set(name, {
            name,
            category,
            execute: async () => { executed.push(name); },
        });
    }
    return { commands, user: { id: 'bot-0' }, voiceManager: {} };
}

function description(reply) {
    return reply.embeds[0].data.description;
}

test.before(() => {
    assert.equal(config.ADMIN_ID, OWNER);
    if (!whitelist.has(LISTED)) whitelist.list.push(LISTED);
});

test.after(() => {
    for (const id of [LISTED]) {
        const at = whitelist.list.indexOf(id);
        if (at > -1) whitelist.list.splice(at, 1);
    }
});

test('the owner runs everything, whitelist or not', async () => {
    for (const command of ['join', 'leave', 'hello', 'wl']) {
        const { msg, replies } = message(OWNER, command);
        const executed = [];
        await handleCommand(client(executed), msg);
        assert.deepEqual(executed, [command], `owner could not run ${command}`);
        assert.equal(replies.length, 0, `owner got a refusal for ${command}`);
    }
});

test('a whitelisted user runs ordinary commands but is refused admin ones', async () => {
    const executed = [];
    const { msg, replies } = message(LISTED, 'join');
    await handleCommand(client(executed), msg);
    assert.deepEqual(executed, ['join']);
    assert.equal(replies.length, 0);

    const admin = message(LISTED, 'wl');
    const executedAdmin = [];
    await handleCommand(client(executedAdmin), admin.msg);
    assert.deepEqual(executedAdmin, [], 'a listed user ran an admin command');
    assert.equal(admin.replies.length, 1, 'the admin refusal went silent');
    assert.match(description(admin.replies[0]), /owner/i);
});

test('a stranger is refused with their id and the way in', async () => {
    const { msg, replies } = message(STRANGER, 'join');
    const executed = [];
    await handleCommand(client(executed), msg);
    assert.deepEqual(executed, [], 'a stranger ran a command');
    assert.equal(replies.length, 1, 'the refusal went silent');
    const text = description(replies[0]);
    assert.ok(text.includes(STRANGER), 'the refusal does not name their id');
    assert.ok(text.includes('!wl add'), 'the refusal does not say how to get in');
});

test('an unknown command is ignored, not answered', async () => {
    const { msg, replies } = message(STRANGER, 'nope');
    await handleCommand(client([]), msg);
    assert.equal(replies.length, 0);
});

test('with no admin configured nobody is the owner', async () => {
    const saved = config.ADMIN_ID;
    config.ADMIN_ID = '';
    try {
        const { msg, replies } = message(OWNER, 'wl');
        const executed = [];
        await handleCommand(client(executed), msg);
        assert.deepEqual(executed, [], 'someone ran admin with no admin configured');
        assert.equal(replies.length, 1);
    } finally {
        config.ADMIN_ID = saved;
    }
});
