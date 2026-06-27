// central config: everything comes from env (set by the python transport)
module.exports = {
    TOKEN: process.env.DISCORD_TOKEN,
    PORT: parseInt(process.env.PORT || '3030', 10),
    BRAIN_API_URL: process.env.BRAIN_API_URL || 'http://127.0.0.1:8000',
    ADMIN_ID: process.env.ADMIN_ID || '',
    INTERRUPT_THRESHOLD_MS: parseInt(process.env.INTERRUPT_THRESHOLD_MS || '2000', 10),
};
