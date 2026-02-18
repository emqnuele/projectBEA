const { EmbedBuilder } = require('discord.js');

function createSuccessEmbed(text) {
    return new EmbedBuilder()
        .setColor(0x00FF00) // green
        .setTitle('✅ Success')
        .setDescription(text);
}

function createErrorEmbed(text) {
    return new EmbedBuilder()
        .setColor(0xFF0000) // red
        .setTitle('❌ Error')
        .setDescription(text);
}

function createWarningEmbed(text) {
    return new EmbedBuilder()
        .setColor(0xFFA500) // orange
        .setTitle('⚠️ Warning')
        .setDescription(text);
}

module.exports = {
    createSuccessEmbed,
    createErrorEmbed,
    createWarningEmbed
};
