const { Client, GatewayIntentBits, Events, EmbedBuilder, Collection, Partials } = require('discord.js');
const { joinVoiceChannel, getVoiceConnection, VoiceConnectionStatus } = require('@discordjs/voice');
const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const { createSuccessEmbed, createErrorEmbed, createWarningEmbed } = require('./utils/embed');

// configuration
const PORT = process.env.PORT || 3030;
const DISCORD_TOKEN = process.env.DISCORD_TOKEN;
const ADMIN_ID = "";
const WHITELIST_FILE = path.join(__dirname, 'whitelist.json');

if (!DISCORD_TOKEN) {
    console.error("Error: DISCORD_TOKEN is not defined in environment variables.");
    process.exit(1);
}

// whitelist management
let whitelist = [];

function loadWhitelist() {
    try {
        if (fs.existsSync(WHITELIST_FILE)) {
            const data = fs.readFileSync(WHITELIST_FILE, 'utf8');
            whitelist = JSON.parse(data);
        } else {
            // create empty if not exists
            saveWhitelist();
        }
        console.log(`Loaded whitelist: ${whitelist.length} users.`);
    } catch (err) {
        console.error("Error loading whitelist:", err);
        whitelist = [];
    }
}

function saveWhitelist() {
    try {
        fs.writeFileSync(WHITELIST_FILE, JSON.stringify(whitelist, null, 2));
    } catch (err) {
        console.error("Error saving whitelist:", err);
    }
}

// load initially
loadWhitelist();

// --- discord client setup ---
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.DirectMessages
    ],
    partials: [Partials.Channel] // required for dms
});

// --- voice manager ---
const VoiceManager = require('./classes/VoiceManager');
client.voiceManager = new VoiceManager(client);

// --- command handling ---
client.commands = new Collection();
const foldersPath = path.join(__dirname, 'commands');
const commandFolders = fs.readdirSync(foldersPath);

for (const folder of commandFolders) {
    const commandsPath = path.join(foldersPath, folder);
    const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.js'));
    for (const file of commandFiles) {
        const filePath = path.join(commandsPath, file);
        const command = require(filePath);
        if ('name' in command && 'execute' in command) {
            client.commands.set(command.name, command);
            console.log(`[INFO] Loaded command ${command.name}`);
        } else {
            console.log(`[WARNING] The command at ${filePath} is missing a required "name" or "execute" property.`);
        }
    }
}

client.once(Events.ClientReady, () => {
    console.log(`Discord Bot ready as ${client.user.tag}`);
});

client.on('messageCreate', async (message) => {
    // ignore bots
    if (message.author.bot) return;

    // check prefix
    if (!message.content.startsWith('!')) return;

    const args = message.content.slice(1).trim().split(/ +/);
    const commandName = args.shift().toLowerCase();

    const command = client.commands.get(commandName);

    if (!command) return;

    const userId = message.author.id;
    const isOwner = userId === ADMIN_ID;
    const isWhitelisted = whitelist.includes(userId);

    // --- access control ---
    // rule:
    // 1. if command is 'wl' (admin category), only admin can use it.
    // 2. for all other commands, user must be whitelisted (including admin).

    // check if command is admin-only (or specifically the 'wl' command)
    if (command.category === 'admin') {
        if (!isOwner) return; // silent ignore
    } else {
        // general/voice commands
        if (!isWhitelisted) return; // silent ignore
    }

    try {
        // execute command
        // we pass a "context" object with shared resources
        const context = {
            client,
            whitelist,
            saveWhitelist,
            isOwner,
            voiceManager: client.voiceManager
        };

        await command.execute(message, args, context);

    } catch (error) {
        console.error(error);
        await message.reply({ embeds: [createErrorEmbed('There was an error executing that command!')] });
    }
});

// --- chat integration (mentions/replies) ---
client.on('messageCreate', async (message) => {
    // Ignore bots
    if (message.author.bot) return;

    // ignore commands (starts with output prefix)
    if (message.content.startsWith('!')) return;

    const userId = message.author.id;
    const isWhitelisted = whitelist.includes(userId);

    // only allow whitelisted users
    if (!isWhitelisted) return;

    // check if mentioned or replying to bot
    const isMentioned = message.mentions.has(client.user.id);
    const isReply = message.reference && message.reference.messageId;
    const isDM = !message.guild;

    // if reply, check if it is replying to the bot
    let isReplyToBot = false;
    if (isReply) {
        try {
            const repliedMessage = await message.channel.messages.fetch(message.reference.messageId);
            if (repliedMessage.author.id === client.user.id) {
                isReplyToBot = true;
            }
        } catch (e) {
            console.error("Failed to fetch replied message", e);
        }
    }

    // in dms, we always respond as long as it's not a command.
    if (isMentioned || isReplyToBot || isDM) {
        // trigger generic typing
        await message.channel.sendTyping();

        // prepare content: remove mention from text if present to avoid confusion
        let cleanContent = message.content.replace(new RegExp(`<@!?${client.user.id}>`, 'g'), '').trim();
        if (!cleanContent) return; // empty message

        // determine best display name: guild nickname > global display name > username
        const displayName = message.member ? message.member.displayName : (message.author.globalName || message.author.username);

        const axios = require('axios');
        try {
            const response = await axios.post(`http://127.0.0.1:${PORT === 3030 ? 8000 : 8000}/discord/chat`, {
                username: displayName,
                message: cleanContent,
                channelId: message.channel.id
            });

            if (response.data && response.data.status === 'success') {
                const replyText = response.data.response;
                await message.reply(replyText);
            }
        } catch (error) {
            console.error("Error talking to Brain:", error.message);
        }
    }
});

// express api setup
const app = express();
app.use(cors());
app.use(bodyParser.json());

// endpoint: check health
app.get('/health', (req, res) => {
    res.json({ status: 'ok', bot_user: client.user ? client.user.tag : null });
});

// endpoint: send message
app.post('/send', async (req, res) => {
    const { channelId, content } = req.body;

    if (!channelId || !content) {
        return res.status(400).json({ error: 'Missing channelId or content' });
    }

    try {
        const channel = await client.channels.fetch(channelId);
        if (!channel) {
            return res.status(404).json({ error: 'Channel not found' });
        }

        if (!channel.isTextBased()) {
            return res.status(400).json({ error: 'Channel is not text-based' });
        }

        const embed = new EmbedBuilder()
            .setColor(0x3498db)
            .setDescription(content)
            .setTimestamp();

        await channel.send({ embeds: [embed] });
        console.log(`Sent message to ${channelId}: ${content}`);
        res.json({ success: true });
    } catch (error) {
        console.error('Error sending message via API:', error);
        res.status(500).json({ error: error.message });
    }
});

// --- start ---
// login discord first, then start server
client.login(DISCORD_TOKEN).then(() => {
    app.listen(PORT, () => {
        console.log(`Bot API listening on port ${PORT}`);
    });
}).catch(err => {
    console.error("Failed to login to Discord:", err);
    process.exit(1);
});
