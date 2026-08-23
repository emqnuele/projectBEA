const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const { ChannelType } = require('discord.js');

// the command API: brain -> bot. Bea's tools hit these endpoints to act on
// discord (speak in text, react, dm, join voice, etc.). Replies are plain text
// (no embeds) so Bea sounds like a person, not a system notification.
function createServer({ client, voiceManager }) {
    const app = express();
    app.use(cors());
    app.use(bodyParser.json());

    const ok = (res, extra = {}) => res.json({ success: true, ...extra });
    const fail = (res, code, error) => res.status(code).json({ error });

    app.get('/health', (req, res) => {
        res.json({ status: 'ok', bot_user: client.user ? client.user.tag : null });
    });

    // --- text ---------------------------------------------------------------

    app.post('/send', async (req, res) => {
        const { channelId, content } = req.body;
        if (!channelId || !content) return fail(res, 400, 'Missing channelId or content');
        try {
            const channel = await client.channels.fetch(channelId);
            if (!channel || !channel.isTextBased()) return fail(res, 400, 'Channel is not text-based');
            const sent = await channel.send(content);
            return ok(res, { messageId: sent.id });
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    app.post('/reply', async (req, res) => {
        const { channelId, messageId, content } = req.body;
        if (!channelId || !messageId || !content) return fail(res, 400, 'Missing channelId, messageId or content');
        try {
            const channel = await client.channels.fetch(channelId);
            if (!channel || !channel.isTextBased()) return fail(res, 400, 'Channel is not text-based');
            const target = await channel.messages.fetch(messageId);
            const sent = await target.reply(content);
            return ok(res, { messageId: sent.id });
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    // "she's writing": shown for ~10s or until the next message lands. The
    // humanizer calls this before each chunk so a multi-line reply reads as
    // someone typing, not as a webhook dumping a paragraph.
    app.post('/typing', async (req, res) => {
        const { channelId } = req.body;
        if (!channelId) return fail(res, 400, 'Missing channelId');
        try {
            const channel = await client.channels.fetch(channelId);
            if (!channel || !channel.isTextBased()) return fail(res, 400, 'Channel is not text-based');
            await channel.sendTyping();
            return ok(res);
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    app.post('/react', async (req, res) => {
        const { channelId, messageId, emoji } = req.body;
        if (!channelId || !messageId || !emoji) return fail(res, 400, 'Missing channelId, messageId or emoji');
        try {
            const channel = await client.channels.fetch(channelId);
            if (!channel || !channel.isTextBased()) return fail(res, 400, 'Channel is not text-based');
            const target = await channel.messages.fetch(messageId);
            await target.react(emoji);
            return ok(res);
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    app.post('/dm', async (req, res) => {
        const { userId, content } = req.body;
        if (!userId || !content) return fail(res, 400, 'Missing userId or content');
        try {
            const user = await client.users.fetch(userId);
            await user.send(content);
            return ok(res);
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    // --- "call" someone: DM them an invite link to a voice channel ----------

    app.post('/summon', async (req, res) => {
        const { userId, channelId, content } = req.body;
        if (!userId || !channelId) return fail(res, 400, 'Missing userId or channelId');
        try {
            const channel = await client.channels.fetch(channelId);
            if (!channel) return fail(res, 404, 'Channel not found');

            let link = `https://discord.com/channels/${channel.guild ? channel.guild.id : '@me'}/${channelId}`;
            try {
                const invite = await channel.createInvite({ maxAge: 0, maxUses: 0 });
                link = invite.url;
            } catch (e) {
                // fall back to the deep link if invites are not permitted
            }

            const user = await client.users.fetch(userId);
            const extra = content ? `${content}\n` : '';
            await user.send(`${extra}**${client.user.username} is calling you!** Join here: ${link}`);
            return ok(res, { link });
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    // --- voice --------------------------------------------------------------

    app.get('/voice/channels', async (req, res) => {
        try {
            const channels = [];
            for (const guild of client.guilds.cache.values()) {
                for (const ch of guild.channels.cache.values()) {
                    if (ch.type !== ChannelType.GuildVoice && ch.type !== ChannelType.GuildStageVoice) continue;
                    const members = [...ch.members.values()].map((m) => ({ id: m.id, name: m.displayName }));
                    channels.push({
                        guildId: guild.id,
                        guildName: guild.name,
                        channelId: ch.id,
                        name: ch.name,
                        members,
                    });
                }
            }
            return res.json({ success: true, channels });
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    app.post('/voice/join', async (req, res) => {
        const { channelId } = req.body;
        if (!channelId) return fail(res, 400, 'Missing channelId');
        try {
            const channel = await client.channels.fetch(channelId);
            if (!channel || (channel.type !== ChannelType.GuildVoice && channel.type !== ChannelType.GuildStageVoice)) {
                return fail(res, 400, 'Not a voice channel');
            }
            const success = await voiceManager.handleJoin(
                channel.guild.id, channel.id, channel.guild.voiceAdapterCreator,
            );
            return success ? ok(res) : fail(res, 500, 'Failed to join voice channel');
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    app.post('/voice/leave', async (req, res) => {
        try {
            voiceManager.leaveAll();
            return ok(res);
        } catch (e) {
            return fail(res, 500, e.message);
        }
    });

    return app;
}

module.exports = { createServer };
