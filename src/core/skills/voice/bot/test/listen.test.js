// A busy port used to reach the owner as an unhandled 'error' event: a v8
// stack trace, three restarts, and then a line blaming DISCORD_TOKEN. The
// reason was that the previous bot had never been stopped.

const test = require('node:test');
const assert = require('node:assert');
const net = require('node:net');
const express = require('express');

const { listen } = require('../api/server');

const HOST = '127.0.0.1';

function freePort() {
    return new Promise((resolve) => {
        const probe = net.createServer();
        probe.listen(0, HOST, () => {
            const { port } = probe.address();
            probe.close(() => resolve(port));
        });
    });
}

test('it listens on a free port', async () => {
    const port = await freePort();
    const server = await new Promise((resolve) => {
        const s = listen(express(), { port, host: HOST, onError: () => {} });
        s.once('listening', () => resolve(s));
    });
    assert.equal(server.address().port, port);
    await new Promise((resolve) => server.close(resolve));
});

test('a port that is already taken is reported, not thrown', async () => {
    const squatter = net.createServer();
    const port = await freePort();
    await new Promise((resolve) => squatter.listen(port, HOST, resolve));

    const err = await new Promise((resolve) => {
        listen(express(), { port, host: HOST, onError: resolve });
    });

    assert.equal(err.code, 'EADDRINUSE');
    await new Promise((resolve) => squatter.close(resolve));
});
