const { joinVoiceChannel } = require('@discordjs/voice');
const { createSuccessEmbed, createErrorEmbed } = require('../../utils/embed');

module.exports = {
    name: 'join',
    description: 'Joins your voice channel',
    category: 'voice',
    async execute(message, args, { voiceManager }) {
        if (!message.member.voice.channel) {
            return message.reply({ embeds: [createErrorEmbed("You need to be in a voice channel first!")] });
        }

        await message.reply({ embeds: [createSuccessEmbed(`Connecting to **${message.member.voice.channel.name}**...`)] });

        const success = await voiceManager.handleJoin(
            message.guild.id,
            message.member.voice.channel.id,
            message.guild.voiceAdapterCreator
        );

        if (success) {
        } else {
            await message.reply({ embeds: [createErrorEmbed("Failed to join voice channel.")] });
        }
    }
};
