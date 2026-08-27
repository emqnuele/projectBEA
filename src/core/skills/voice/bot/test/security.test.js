// The command API can write as Bea, DM anyone she can see and mint invites.
// It used to accept every request from every interface. These tests are the
// proof it no longer does.

const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');

const { requireToken, inviteOptions } = require('../api/guard');
const { createServer } = require('../api/server');

// --- the guard, on its own --------------------------------------------------

test('a request without a token is refused', () => {
    const guard = requireToken('s3cret');
    const res = fakeRes();
    let passed = false;
    guard({ headers: {}, path: '/send' }, res, () => { passed = true; });
    assert.equal(passed, false);
    assert.equal(res.code, 401);
});

test('a request with the wrong token is refused', () => {
    const guard = requireToken('s3cret');
    const res = fakeRes();
    let passed = false;
    guard({ headers: { authorization: 'Bearer nope' }, path: '/send' }, res, () => { passed = true; });
    assert.equal(passed, false);
    assert.equal(res.code, 401);
});

test('a request with the right token goes through', () => {
    const guard = requireToken('s3cret');
    const res = fakeRes();
    let passed = false;
    guard({ headers: { authorization: 'Bearer s3cret' }, path: '/send' }, res, () => { passed = true; });
    assert.equal(passed, true);
    assert.equal(res.code, null);
});

test('an unconfigured token refuses everything rather than allowing it', () => {
    const guard = requireToken('');
    const res = fakeRes();
    let passed = false;
    guard({ headers: { authorization: 'Bearer ' }, path: '/send' }, res, () => { passed = true; });
    assert.equal(passed, false);
    assert.equal(res.code, 503);
});

// --- invites ----------------------------------------------------------------

test('invites expire and are single use by default', () => {
    const opts = inviteOptions({});
    assert.equal(opts.maxAge, 3600);
    assert.equal(opts.maxUses, 1);
});

test('invites can be widened but never made permanent', () => {
    const opts = inviteOptions({ INVITE_MAX_AGE: '0', INVITE_MAX_USES: '0' });
    assert.ok(opts.maxAge > 0, 'maxAge 0 means an invite that never expires');
    assert.ok(opts.maxUses > 0, 'maxUses 0 means an invite anyone can reuse forever');
});

test('invite settings from the environment are honoured', () => {
    const opts = inviteOptions({ INVITE_MAX_AGE: '900', INVITE_MAX_USES: '5' });
    assert.equal(opts.maxAge, 900);
    assert.equal(opts.maxUses, 5);
});

// --- the server it is wired into --------------------------------------------

test('the server refuses an unauthenticated send', async () => {
    const { port, close } = await listen();
    try {
        const res = await post(port, '/send', { channelId: '1', content: 'ciao' }, {});
        assert.equal(res.status, 401);
    } finally {
        await close();
    }
});

test('the server accepts an authenticated send', async () => {
    const { port, close, sent } = await listen();
    try {
        const res = await post(port, '/send', { channelId: '1', content: 'ciao' },
            { authorization: 'Bearer test-token' });
        assert.equal(res.status, 200);
        assert.deepEqual(sent, [['1', 'ciao']]);
    } finally {
        await close();
    }
});

test('health needs the token too', async () => {
    const { port, close } = await listen();
    try {
        const res = await get(port, '/health', {});
        assert.equal(res.status, 401);
    } finally {
        await close();
    }
});

// --- helpers ----------------------------------------------------------------

function fakeRes() {
    const res = { code: null, body: null };
    res.status = (c) => { res.code = c; return res; };
    res.json = (b) => { res.body = b; return res; };
    return res;
}

function fakeClient(sent) {
    const channel = {
        isTextBased: () => true,
        send: async (content) => { sent.push([channel.id, content]); return { id: 'm1' }; },
        sendTyping: async () => {},
        messages: { fetch: async () => ({ reply: async () => ({ id: 'm2' }), react: async () => {} }) },
    };
    return {
        user: { tag: 'bea#0001', username: 'bea', id: 'bot' },
        guilds: { cache: new Map() },
        channels: { fetch: async (id) => { channel.id = id; return channel; } },
        users: { fetch: async () => ({ send: async () => {} }) },
    };
}

async function listen() {
    const sent = [];
    const app = createServer({
        client: fakeClient(sent),
        voiceManager: { handleJoin: async () => true, leaveAll: () => {} },
        token: 'test-token',
    });
    const server = await new Promise((resolve) => {
        const s = app.listen(0, '127.0.0.1', () => resolve(s));
    });
    return {
        port: server.address().port,
        sent,
        close: () => new Promise((r) => server.close(r)),
    };
}

function request(port, method, path, body, headers) {
    return new Promise((resolve, reject) => {
        const payload = body ? JSON.stringify(body) : null;
        const req = http.request({
            host: '127.0.0.1', port, path, method,
            headers: {
                ...(payload ? { 'content-type': 'application/json', 'content-length': Buffer.byteLength(payload) } : {}),
                ...headers,
            },
        }, (res) => {
            let data = '';
            res.on('data', (c) => { data += c; });
            res.on('end', () => resolve({ status: res.statusCode, body: data }));
        });
        req.on('error', reject);
        if (payload) req.write(payload);
        req.end();
    });
}

const post = (port, path, body, headers) => request(port, 'POST', path, body, headers);
const get = (port, path, headers) => request(port, 'GET', path, null, headers);
