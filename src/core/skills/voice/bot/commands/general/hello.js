const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'hello',
    description: 'Greets the user',
    category: 'general',
    async execute(message, args, { client }) {
        const embed = new EmbedBuilder()
            .setColor(0x00FF00)
            .setTitle('Hello!')
            .setDescription(`Hi there, ${message.author.username}! I am Bea.`)
            .setThumbnail(client.user.displayAvatarURL())
            .setTimestamp();

        await message.reply({ embeds: [embed] });
    }
};
