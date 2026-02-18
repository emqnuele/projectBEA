const {
    joinVoiceChannel,
    getVoiceConnection,
    VoiceConnectionStatus,
    EndBehaviorType,
    createAudioPlayer,
    createAudioResource,
    StreamType,
    AudioPlayerStatus
} = require('@discordjs/voice');
const prism = require('prism-media');
const axios = require('axios');
const fs = require('fs');
const FormData = require('form-data');
const { Readable } = require('stream');

class VoiceManager {
    constructor(client) {
        this.client = client;
        this.connections = new Map(); // guildId -> connection data
        this.apiBaseUrl = process.env.BRAIN_API_URL || 'http://127.0.0.1:8000';

        // sustained-speech threshold: only interrupt bea if someone talks for this long
        // each frame is ~20ms, so 2000ms = 100 frames
        this.INTERRUPT_THRESHOLD_MS = 2000;
    }

    async handleJoin(guildId, channelId, adapterCreator) {
        try {
            const connection = joinVoiceChannel({
                channelId: channelId,
                guildId: guildId,
                adapterCreator: adapterCreator,
                selfDeaf: false,
                selfMute: false
            });

            const player = createAudioPlayer();
            connection.subscribe(player);

            const connectionData = {
                connection,
                player,
                isSpeaking: false, // true when bea is actively playing audio
                subscriptions: new Map() // userid -> opusstream
            };

            this.connections.set(guildId, connectionData);

            // handle player events for speaking state tracking
            player.on(AudioPlayerStatus.Playing, () => {
                connectionData.isSpeaking = true;
                console.log('[VoiceManager] Bea: SPEAKING');
            });
            player.on(AudioPlayerStatus.Idle, () => {
                connectionData.isSpeaking = false;
                console.log('[VoiceManager] Bea: IDLE');
            });
            player.on(AudioPlayerStatus.Paused, () => {
                connectionData.isSpeaking = false;
                console.log('[VoiceManager] Bea: PAUSED');
            });

            connection.on(VoiceConnectionStatus.Ready, () => {
                console.log(`[VoiceManager] Connection ready in guild ${guildId}`);
                this.listenToUsers(guildId);
            });

            connection.on(VoiceConnectionStatus.Disconnected, () => {
                console.log(`[VoiceManager] Disconnected from guild ${guildId}`);
                this.cleanup(guildId);
            });

            return true;
        } catch (error) {
            console.error(`[VoiceManager] Error joining:`, error);
            return false;
        }
    }

    handleLeave(guildId) {
        const data = this.connections.get(guildId);
        if (data && data.connection) {
            data.connection.destroy();
        }
        this.cleanup(guildId);
    }

    cleanup(guildId) {
        const data = this.connections.get(guildId);
        if (data) {
            if (data.player) data.player.stop();
            // stop all streams
            for (const [userId, stream] of data.subscriptions) {
                stream.destroy();
            }
            this.connections.delete(guildId);
        }
    }

    listenToUsers(guildId) {
        const data = this.connections.get(guildId);
        if (!data) return;

        const receiver = data.connection.receiver;

        // monitor who is speaking
        receiver.speaking.on('start', (userId) => {
            if (data.subscriptions.has(userId)) return;
            console.log(`[VoiceManager] User ${userId} started speaking`);
            this.createStream(guildId, userId);
        });
    }

    createStream(guildId, userId) {
        const data = this.connections.get(guildId);
        if (!data) return;

        const opusStream = data.connection.receiver.subscribe(userId, {
            end: {
                behavior: EndBehaviorType.AfterSilence,
                duration: 100, // fast but safe: opus frames are 20ms, need margin to not clip words
            },
        });

        // save stream
        data.subscriptions.set(userId, opusStream);

        // decode opus to pcm (signed 16-bit little endian, 48khz, stereo)
        const decoder = new prism.opus.Decoder({ frameSize: 960, channels: 2, rate: 48000 });
        const pcmStream = opusStream.pipe(decoder);

        const chunks = [];

        // vad state: noise gate
        let speechFrameCount = 0;
        const VAD_THRESHOLD = 800; // ignore typing clicks / background noise
        const MIN_SPEECH_FRAMES = 6; // require 120ms of sustained volume (6 * 20ms)

        // sustained-speech interrupt detection
        // each frame is ~20ms. we track if the user has been speaking long enough to interrupt bea.
        const interruptFrameThreshold = Math.floor(this.INTERRUPT_THRESHOLD_MS / 20);
        let didInterrupt = false;

        const beaWasSpeaking = data.isSpeaking;

        pcmStream.on('data', (chunk) => {
            chunks.push(chunk);

            // analyze energy
            const rms = this.calculateRMS(chunk);
            if (rms > VAD_THRESHOLD) {
                speechFrameCount++;

                // live interrupt check: only if bea is currently playing audio
                if (!didInterrupt && data.isSpeaking && speechFrameCount >= interruptFrameThreshold) {
                    console.log(`[VoiceManager] Sustained speech (${(speechFrameCount * 20 / 1000).toFixed(1)}s) — INTERRUPTING Bea`);
                    data.player.stop();
                    axios.post(`${this.apiBaseUrl}/interrupt`).catch(e => { });
                    didInterrupt = true;
                }
            }
        });

        pcmStream.on('end', async () => {
            // clean up
            data.subscriptions.delete(userId);
            const speechDurationMs = speechFrameCount * 20;
            console.log(`[VoiceManager] Stream ended. Speech: ${speechDurationMs}ms (${speechFrameCount} frames), beaWasSpeaking=${beaWasSpeaking}, isSpeaking=${data.isSpeaking}`);

            // 1. noise filter: if audio was too short or too quiet
            if (speechFrameCount < MIN_SPEECH_FRAMES) {
                console.log("[VoiceManager] Discarding noise (Keyboard/Background).");
                return;
            }

            // 2. valid speech — determine how to handle it
            if (chunks.length === 0) return;

            const totalBuffer = Buffer.concat(chunks);

            // key logic: behavior depends on whether bea was speaking
            if (!beaWasSpeaking && !data.isSpeaking) {
                // bea is idle → process all valid speech immediately, no threshold needed
                console.log(`[VoiceManager] Bea is idle → sending to full LLM pipeline`);
                await this.processAudio(guildId, userId, totalBuffer, true);
            } else if (speechDurationMs >= this.INTERRUPT_THRESHOLD_MS || didInterrupt) {
                // bea was speaking but user talked long enough to interrupt
                console.log(`[VoiceManager] Sustained speech interrupted Bea → full LLM pipeline`);
                await this.processAudio(guildId, userId, totalBuffer, true);
            } else {
                // bea is speaking and user speech was short → buffer only
                console.log(`[VoiceManager] Short speech while Bea talks → buffering transcript`);
                await this.bufferTranscript(guildId, userId, totalBuffer);
            }
        });

        pcmStream.on('error', (err) => {
            console.error(`[VoiceManager] Stream error for ${userId}:`, err);
            data.subscriptions.delete(userId);
        });
    }

    calculateRMS(buffer) {
        let sum = 0;
        const len = buffer.length / 2;
        if (len === 0) return 0;

        for (let i = 0; i < buffer.length; i += 2) {
            const int16 = buffer.readInt16LE(i);
            sum += int16 * int16;
        }
        return Math.sqrt(sum / len);
    }

    /**
     * buffer a short transcript without triggering llm.
     * transcribes locally then sends to /voice/transcript for accumulation.
     */
    async bufferTranscript(guildId, userId, pcmBuffer) {
        // 1. fetch username
        let username = userId;
        try {
            const guild = await this.client.guilds.fetch(guildId);
            const member = await guild.members.fetch(userId);
            username = member.displayName;
        } catch (e) {
            console.error("Error fetching user:", e);
        }

        // 2. convert pcm to wav
        const wavBuffer = this.pcmToWav(pcmBuffer, 48000, 2);

        // 3. send to /voice/transcript (buffer-only endpoint)
        try {
            const form = new FormData();
            form.append('file', wavBuffer, { filename: 'audio.wav', contentType: 'audio/wav' });
            form.append('username', username);

            const response = await axios.post(`${this.apiBaseUrl}/voice/transcript`, form, {
                headers: { ...form.getHeaders() }
            });

            console.log(`[VoiceManager] Transcript buffered for ${username}: ${response.data.transcript || '(empty)'}`);
        } catch (error) {
            console.error("[VoiceManager] Buffer transcript error:", error.message);
        }
    }

    async processAudio(guildId, userId, pcmBuffer, flushBuffer = false) {
        const data = this.connections.get(guildId);

        // 1. fetch user info
        let username = userId;
        try {
            const guild = await this.client.guilds.fetch(guildId);
            const member = await guild.members.fetch(userId);
            username = member.displayName;
        } catch (e) {
            console.error("Error fetching user:", e);
        }

        console.log(`[VoiceManager] Processing audio from ${username} (${pcmBuffer.length} bytes, flush=${flushBuffer})`);

        // 2. convert pcm to wav
        const wavBuffer = this.pcmToWav(pcmBuffer, 48000, 2);

        // 3. send to backend
        try {
            const form = new FormData();
            form.append('file', wavBuffer, { filename: 'audio.wav', contentType: 'audio/wav' });
            form.append('username', username);
            if (flushBuffer) {
                form.append('flush_buffer', 'true');
            }

            const response = await axios.post(`${this.apiBaseUrl}/discord/audio`, form, {
                headers: { ...form.getHeaders() }
            });

            const { status, text, audio_base64 } = response.data;

            if (status === 'success') {
                // new response -> stop old, play new
                if (data && data.player) {
                    data.player.stop(); // Stop potential paused content
                    console.log(`[VoiceManager] Response: "${text}"`);
                    if (audio_base64) {
                        this.playAudio(guildId, audio_base64);
                    }
                }
            } else if (status === 'resume') {
                // backchannel -> resume old content
                console.log(`[VoiceManager] Backchannel detected: "${text}". Resuming...`);
                if (data && data.player && data.player.state.status === AudioPlayerStatus.Paused) {
                    data.player.unpause();
                }
            }

        } catch (error) {
            console.error("[VoiceManager] API Error:", error.message);
            if (data && data.player && data.player.state.status === AudioPlayerStatus.Paused) {
                data.player.unpause();
            }
        }
    }

    playAudio(guildId, base64Audio) {
        const data = this.connections.get(guildId);
        if (!data || !data.player) return;

        try {
            const buffer = Buffer.from(base64Audio, 'base64');

            // create readable stream
            const stream = Readable.from(buffer);

            const resource = createAudioResource(stream, {
                inputType: StreamType.Arbitrary
            });

            data.player.play(resource);

        } catch (e) {
            console.error("[VoiceManager] Playback Logic Error:", e);
        }
    }

    // helper: add wav header
    pcmToWav(pcmData, sampleRate, numChannels) {
        const header = Buffer.alloc(44);
        const byteRate = sampleRate * numChannels * 2; // 16-bit = 2 bytes
        const blockAlign = numChannels * 2;
        const subChunk2Size = pcmData.length;
        const chunkSize = 36 + subChunk2Size;

        header.write('RIFF', 0);
        header.writeUInt32LE(chunkSize, 4);
        header.write('WAVE', 8);

        header.write('fmt ', 12);
        header.writeUInt32LE(16, 16);
        header.writeUInt16LE(1, 20);
        header.writeUInt16LE(numChannels, 22);
        header.writeUInt32LE(sampleRate, 24);
        header.writeUInt32LE(byteRate, 28);
        header.writeUInt16LE(blockAlign, 32);
        header.writeUInt16LE(16, 34);

        header.write('data', 36);
        header.writeUInt32LE(subChunk2Size, 40);

        return Buffer.concat([header, pcmData]);
    }
}

module.exports = VoiceManager;
