const { Client, GatewayIntentBits, Events, Collection, Partials } = require('discord.js');
const fs = require('fs');
const path = require('path');

const config = require('./config');
const whitelist = require('./whitelist');
const messageHandler = require('./handlers/messages');
const { createServer } = require('./api/server');
const VoiceManager = require('./classes/VoiceManager');

if (!config.TOKEN) {
    console.error('Error: DISCORD_TOKEN is not defined in environment variables.');
    process.exit(1);
}

whitelist.load();

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.DirectMessages,
    ],
    partials: [Partials.Channel], // required for dms
});

client.voiceManager = new VoiceManager(client);

// --- command loading ---
client.commands = new Collection();
const foldersPath = path.join(__dirname, 'commands');
for (const folder of fs.readdirSync(foldersPath)) {
    const commandsPath = path.join(foldersPath, folder);
    const files = fs.readdirSync(commandsPath).filter((f) => f.endsWith('.js'));
    for (const file of files) {
        const command = require(path.join(commandsPath, file));
        if ('name' in command && 'execute' in command) {
            client.commands.set(command.name, command);
            console.log(`[INFO] Loaded command ${command.name}`);
        } else {
            console.log(`[WARNING] Command at ${file} is missing "name" or "execute".`);
        }
    }
}

client.once(Events.ClientReady, () => {
    console.log(`Discord Bot ready as ${client.user.tag}`);
});

messageHandler.register(client);

// --- start: login, then expose the command API ---
client.login(config.TOKEN).then(() => {
    const app = createServer({ client, voiceManager: client.voiceManager });
    app.listen(config.PORT, () => {
        console.log(`Bot API listening on port ${config.PORT}`);
    });
}).catch((err) => {
    console.error('Failed to login to Discord:', err);
    process.exit(1);
});
