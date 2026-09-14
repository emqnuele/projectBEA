// Runtime state lives in data/, not in the source tree: a tracked file the
// bot rewrites on every `!wl` used to read as local changes and block the
// updater.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bea-wl-'));
process.env.BEA_DATA_DIR = dir;

const whitelist = require('../whitelist');

test('saves into BEA_DATA_DIR instead of the source tree', () => {
    whitelist.load();
    whitelist.list.push('user-1');
    try {
        whitelist.save();
        const file = path.join(dir, 'discord_whitelist.json');
        assert.ok(fs.existsSync(file), `nothing was written to ${file}`);
        assert.ok(JSON.parse(fs.readFileSync(file, 'utf8')).includes('user-1'));
        assert.ok(whitelist.has('user-1'));
    } finally {
        const at = whitelist.list.indexOf('user-1');
        if (at > -1) whitelist.list.splice(at, 1);
        fs.rmSync(dir, { recursive: true, force: true });
    }
});
