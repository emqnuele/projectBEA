const { getVoiceConnection } = require('@discordjs/voice');
const { createSuccessEmbed, createErrorEmbed, createWarningEmbed } = require('../../utils/embed');

module.exports = {
    name: 'leave',
    description: 'Leaves the voice channel',
    category: 'voice',
    async execute(message, args, { voiceManager }) {
        voiceManager.handleLeave(message.guild.id);
        await message.reply({ embeds: [createSuccessEmbed("Disconnected from voice channel.")] });
    }
};
