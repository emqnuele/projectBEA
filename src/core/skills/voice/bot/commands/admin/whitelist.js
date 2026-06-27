const { EmbedBuilder } = require('discord.js');
const { createSuccessEmbed, createErrorEmbed, createWarningEmbed } = require('../../utils/embed');

module.exports = {
    name: 'wl',
    description: 'Manage whitelist',
    category: 'admin',
    async execute(message, args, { whitelist, saveWhitelist, isOwner }) {
        // double check owner just in case, though handler should block it too
        if (!isOwner) return;

        const command = args[0];
        let targetId = args[1];

        // helper to strip mention formatting (<@123...>)
        if (targetId) {
            targetId = targetId.replace(/[<@!>]/g, '');
        }

        if (command === 'add') {
            if (!targetId) {
                return message.reply({ embeds: [createErrorEmbed("Usage: `!wl add <userId>` (You can mention the user)")] });
            }
            if (!whitelist.includes(targetId)) {
                whitelist.push(targetId);
                saveWhitelist();
                return message.reply({ embeds: [createSuccessEmbed(`User <@${targetId}> (${targetId}) added to whitelist.`)] });
            } else {
                return message.reply({ embeds: [createWarningEmbed("User is already whitelisted.")] });
            }
        } else if (command === 'remove') {
            if (!targetId) {
                return message.reply({ embeds: [createErrorEmbed("Usage: `!wl remove <userId>`")] });
            }
            if (whitelist.includes(targetId)) {
                const index = whitelist.indexOf(targetId);
                if (index > -1) {
                    whitelist.splice(index, 1);
                    saveWhitelist();
                    return message.reply({ embeds: [createSuccessEmbed(`User <@${targetId}> (${targetId}) removed from whitelist.`)] });
                }
            } else {
                return message.reply({ embeds: [createWarningEmbed("User is not in whitelist.")] });
            }
        } else if (command === 'list') {
            const listContent = whitelist.map(id => `- <@${id}> (${id})`).join('\n') || "Empty";
            const embed = new EmbedBuilder()
                .setColor(0x0099FF)
                .setTitle('📜 Whitelisted Users')
                .setDescription(listContent)
                .setTimestamp();
            return message.reply({ embeds: [embed] });
        } else {
            return message.reply({ embeds: [createErrorEmbed("Unknown subcommand. Use `add`, `remove`, or `list`.")] });
        }
    }
};
