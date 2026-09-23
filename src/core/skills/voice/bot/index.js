const { Client, GatewayIntentBits, Events, Collection, Partials } = require('discord.js');
const fs = require('fs');
const path = require('path');

const config = require('./config');
const whitelist = require('./whitelist');
const messageHandler = require('./handlers/messages');
const { createServer, listen } = require('./api/server');
const VoiceManager = require('./classes/VoiceManager');

if (!config.TOKEN) {
    console.error('Error: DISCORD_TOKEN is not defined in environment variables.');
    process.exit(1);
}

if (!config.API_TOKEN) {
    console.error('Error: API_TOKEN is not defined. The bot is started by the python transport, which mints it.');
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
let apiServer = null;
client.login(config.TOKEN).then(() => {
    const app = createServer({
        client,
        voiceManager: client.voiceManager,
        token: config.API_TOKEN,
    });
    // BIND_HOST is loopback: the API has no business being on the network
    apiServer = listen(app, {
        port: config.PORT,
        host: config.BIND_HOST,
        // a bot that is logged in but unreachable is worse than no bot: the
        // brain would keep handing it work it cannot do
        onError: () => {
            client.destroy();
            process.exit(1);
        },
    });
}).catch((err) => {
    console.error('Failed to login to Discord:', err);
    process.exit(1);
});

// the transport stops the bot with SIGTERM on shutdown: leave the call and
// the gateway cleanly instead of vanishing mid-word. A second signal means
// now rather than cleanly.
let shuttingDown = false;
function shutdown(signal) {
    if (shuttingDown) {
        process.exit(1);
    }
    shuttingDown = true;
    console.log(`Received ${signal}; leaving voice and disconnecting.`);
    try {
        if (apiServer) apiServer.close();
        client.voiceManager.link.stop();
        client.voiceManager.leaveAll();
    } catch (e) {
        console.error('Error during shutdown:', e.message);
    }
    client.destroy().finally(() => process.exit(0));
    // a gateway that never answers must not hold the exit hostage
    setTimeout(() => process.exit(0), 3000).unref();
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
