const fs = require('fs');
const path = require('path');

// runtime state lives outside the source tree, in data/: a tracked file the
// bot rewrites on every `!wl` reads as local changes and blocks the updater.
// explicit env override first (the python transport sets it), then the data
// directory of this checkout, so the bot works when started by hand too.
function resolveWhitelistFile() {
    if (process.env.BEA_DATA_DIR) {
        return path.join(process.env.BEA_DATA_DIR, 'discord_whitelist.json');
    }
    if (process.env.WHITELIST_FILE) {
        return process.env.WHITELIST_FILE;
    }
    const root = path.resolve(__dirname, '..', '..', '..', '..', '..');
    return path.join(root, 'data', 'discord_whitelist.json');
}

// where the list lived before it moved out of the source tree. read once for
// the migration, then left alone.
const LEGACY_FILE = path.join(__dirname, 'whitelist.json');

let WHITELIST_FILE = resolveWhitelistFile();

// kept as a single shared array reference so the command modules (which receive
// it through the context object) keep working unchanged
let whitelist = [];

function readList(file) {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function load() {
    WHITELIST_FILE = resolveWhitelistFile();
    try {
        if (fs.existsSync(WHITELIST_FILE)) {
            whitelist.length = 0;
            whitelist.push(...readList(WHITELIST_FILE));
        } else if (fs.existsSync(LEGACY_FILE)) {
            whitelist.length = 0;
            whitelist.push(...readList(LEGACY_FILE));
            save();
        } else {
            save();
        }
        console.log(`Loaded whitelist: ${whitelist.length} users.`);
    } catch (err) {
        console.error('Error loading whitelist:', err);
        whitelist.length = 0;
    }
}

function save() {
    try {
        fs.mkdirSync(path.dirname(WHITELIST_FILE), { recursive: true });
        fs.writeFileSync(WHITELIST_FILE, JSON.stringify(whitelist, null, 2));
    } catch (err) {
        console.error('Error saving whitelist:', err);
    }
}

function has(userId) {
    return whitelist.includes(userId);
}

module.exports = { load, save, has, list: whitelist };
