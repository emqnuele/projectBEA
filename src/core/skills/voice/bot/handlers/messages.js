const axios = require('axios');
const { Events } = require('discord.js');
const { createErrorEmbed } = require('../utils/embed');
const config = require('../config');
const whitelist = require('../whitelist');

// single messageCreate handler: routes `!commands` and forwards plain chat to
// the brain as a perception (Bea answers autonomously via her discord tools).
function register(client) {
    client.on(Events.MessageCreate, async (message) => {
        if (message.author.bot) return;

        if (message.content.startsWith('!')) {
            return handleCommand(client, message);
        }
        return handleChat(client, message);
    });
}

async function handleCommand(client, message) {
    const args = message.content.slice(1).trim().split(/ +/);
    const commandName = args.shift().toLowerCase();
    const command = client.commands.get(commandName);
    if (!command) return;

    const userId = message.author.id;
    const isOwner = userId === config.ADMIN_ID;

    // admin commands: owner only. everything else: whitelisted only.
    if (command.category === 'admin') {
        if (!isOwner) return;
    } else if (!whitelist.has(userId)) {
        return;
    }

    try {
        await command.execute(message, args, {
            client,
            whitelist: whitelist.list,
            saveWhitelist: whitelist.save,
            isOwner,
            voiceManager: client.voiceManager,
        });
    } catch (error) {
        console.error(error);
        await message.reply({ embeds: [createErrorEmbed('There was an error executing that command!')] });
    }
}

async function handleChat(client, message) {
    const userId = message.author.id;
    if (!whitelist.has(userId)) return;

    const isMentioned = message.mentions.has(client.user.id);
    const isDM = !message.guild;

    let isReplyToBot = false;
    if (message.reference && message.reference.messageId) {
        try {
            const replied = await message.channel.messages.fetch(message.reference.messageId);
            isReplyToBot = replied.author.id === client.user.id;
        } catch (e) {
            console.error('Failed to fetch replied message', e);
        }
    }

    // only react when addressed: a mention, a reply to Bea, or a DM
    if (!(isMentioned || isReplyToBot || isDM)) return;

    const cleanContent = message.content
        .replace(new RegExp(`<@!?${client.user.id}>`, 'g'), '')
        .trim();
    if (!cleanContent) return;

    const displayName = message.member
        ? message.member.displayName
        : (message.author.globalName || message.author.username);

    // deposit a perception and return: Bea decides whether/how to answer and
    // calls discord_reply / discord_send_message herself (no synchronous reply)
    try {
        await axios.post(`${config.BRAIN_API_URL}/discord/chat`, {
            username: displayName,
            message: cleanContent,
            channelId: message.channel.id,
            userId: userId,
            messageId: message.id,
            isDm: isDM,
        });
    } catch (error) {
        console.error('Error talking to Brain:', error.message);
    }
}

module.exports = { register };
