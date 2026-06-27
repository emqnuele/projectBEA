const fs = require('fs');
const path = require('path');

const WHITELIST_FILE = path.join(__dirname, 'whitelist.json');

// kept as a single shared array reference so the command modules (which receive
// it through the context object) keep working unchanged
let whitelist = [];

function load() {
    try {
        if (fs.existsSync(WHITELIST_FILE)) {
            whitelist.length = 0;
            whitelist.push(...JSON.parse(fs.readFileSync(WHITELIST_FILE, 'utf8')));
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
        fs.writeFileSync(WHITELIST_FILE, JSON.stringify(whitelist, null, 2));
    } catch (err) {
        console.error('Error saving whitelist:', err);
    }
}

function has(userId) {
    return whitelist.includes(userId);
}

module.exports = { load, save, has, list: whitelist };
