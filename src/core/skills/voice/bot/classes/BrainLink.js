const WebSocket = require('ws');
const config = require('../config');

// the frame the brain sends: [uint32 header length][header json][pcm payload]
function unframe(data) {
    if (data.length < 4) return null;
    const size = data.readUInt32BE(0);
    if (data.length < 4 + size) return null;
    try {
        return { header: JSON.parse(data.subarray(4, 4 + size).toString('utf8')), payload: data.subarray(4 + size) };
    } catch (e) {
        return null;
    }
}

/**
 * the socket her voice comes down.
 *
 * before this the bot could only hear her by asking a question and waiting on
 * the answer of its own http request, so she could reply and nothing else. this
 * link is open the whole time she is up, which is what lets her start talking.
 *
 * it reconnects on its own: a brain restart must not leave her mute until
 * someone notices.
 */
class BrainLink {
    constructor(voiceManager) {
        this.voiceManager = voiceManager;
        this.url = config.BRAIN_API_URL.replace(/^http/, 'ws') + '/voice/ws';
        this.ws = null;
        this.closed = false;
        this.backoffMs = 500;
    }

    get open() {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }

    start() {
        if (this.closed) return;
        const ws = new WebSocket(this.url, { headers: { Authorization: `Bearer ${config.API_TOKEN}` } });
        this.ws = ws;

        ws.on('open', () => {
            console.log('[BrainLink] voice channel open');
            this.backoffMs = 500;
            this.voiceManager.announceCall();
        });
        ws.on('message', (data, isBinary) => this.dispatch(data, isBinary));
        ws.on('close', () => this.retry('closed'));
        ws.on('error', (err) => this.retry(err.message));
    }

    retry(why) {
        if (this.ws) this.ws.removeAllListeners();
        this.ws = null;
        if (this.closed) return;
        console.log(`[BrainLink] voice channel down (${why}); retrying in ${this.backoffMs}ms`);
        setTimeout(() => this.start(), this.backoffMs);
        // back off, but never so far that a restart leaves her mute for a minute
        this.backoffMs = Math.min(this.backoffMs * 2, 10000);
    }

    stop() {
        this.closed = true;
        if (this.ws) this.ws.close();
        this.ws = null;
    }

    dispatch(data, isBinary) {
        if (isBinary) {
            const frame = unframe(data);
            if (frame && frame.header.type === 'play') {
                this.voiceManager.playPushed(frame.header, frame.payload);
            }
            return;
        }
        let message;
        try {
            message = JSON.parse(data.toString('utf8'));
        } catch (e) {
            return;
        }
        if (message.type === 'stop') this.voiceManager.stopSpeaking(message.ramp_ms);
        else if (message.type === 'duck') this.voiceManager.duck(message.gain, message.ramp_ms);
        else if (message.type === 'cancel') this.voiceManager.cancelPending();
    }

    send(message) {
        if (!this.open) return false;
        try {
            this.ws.send(JSON.stringify(message));
            return true;
        } catch (e) {
            console.error('[BrainLink] send failed:', e.message);
            return false;
        }
    }
}

module.exports = { BrainLink, unframe };
