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
const FormData = require('form-data');
const { PassThrough } = require('stream');
const config = require('../config');
const whitelist = require('../whitelist');
const { BrainLink } = require('./BrainLink');
const { PcmGain } = require('./PcmGain');

class VoiceManager {
    constructor(client) {
        this.client = client;
        this.connections = new Map(); // guildId -> connection data
        this.apiBaseUrl = config.BRAIN_API_URL;

        // sustained-speech threshold: only interrupt bea if someone talks for this long
        this.INTERRUPT_THRESHOLD_MS = config.INTERRUPT_THRESHOLD_MS;

        // her voice arrives here, whenever she decides to speak
        this.link = new BrainLink(this);
        this.link.start();

        // people coming and going changes how she should read the room
        client.on('voiceStateUpdate', () => this.announceCall());
    }

    // she is in at most one call at a time
    currentGuild() {
        return [...this.connections.keys()][0] || null;
    }

    // leave every voice channel we're connected to (the discord_leave_voice tool)
    leaveAll() {
        for (const guildId of [...this.connections.keys()]) {
            this.handleLeave(guildId);
        }
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
                channelId,
                isSpeaking: false, // true when bea is actively playing audio
                speech: null,      // the utterance currently on the wire
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
                this.finishUtterance(guildId, 'done');
            });
            player.on(AudioPlayerStatus.Paused, () => {
                connectionData.isSpeaking = false;
                console.log('[VoiceManager] Bea: PAUSED');
            });

            connection.on(VoiceConnectionStatus.Ready, () => {
                console.log(`[VoiceManager] Connection ready in guild ${guildId}`);
                this.listenToUsers(guildId);
                this.announceCall();
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
            this.finishUtterance(guildId, 'stopped');
            if (data.player) data.player.stop();
            // stop all streams
            for (const [userId, stream] of data.subscriptions) {
                stream.destroy();
            }
            this.connections.delete(guildId);
        }
        this.announceCall();
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
                    // a ramp, not a cut: the brain hears back how far she got
                    this.stopSpeaking(200);
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
                await this.processAudio(guildId, userId, totalBuffer);
            } else if (speechDurationMs >= this.INTERRUPT_THRESHOLD_MS || didInterrupt) {
                // bea was speaking but user talked long enough to interrupt
                console.log(`[VoiceManager] Sustained speech interrupted Bea → full LLM pipeline`);
                await this.processAudio(guildId, userId, totalBuffer);
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
        const username = await this.displayNameOf(guildId, userId);

        // downsample to mono 16khz and wrap as wav (smaller, enough for stt)
        const wavBuffer = this.pcmToWav(this.downsampleMono16k(pcmBuffer), 16000, 1);

        try {
            const form = this.speechForm(wavBuffer, guildId, userId, username);
            const response = await axios.post(`${this.apiBaseUrl}/voice/transcript`, form,
                { headers: form.getHeaders() });
            console.log(`[VoiceManager] Overheard from ${username}: ${response.data.transcript || '(empty)'}`);
        } catch (error) {
            console.error("[VoiceManager] Overheard transcript error:", error.message);
        }
    }

    async processAudio(guildId, userId, pcmBuffer) {
        const username = await this.displayNameOf(guildId, userId);

        console.log(`[VoiceManager] Processing audio from ${username} (${pcmBuffer.length} bytes)`);

        // downsample to mono 16khz and wrap as wav
        const wavBuffer = this.pcmToWav(this.downsampleMono16k(pcmBuffer), 16000, 1);

        // nothing comes back from here: whatever she decides to say arrives on
        // the push channel, on her clock rather than on this request's
        try {
            const form = this.speechForm(wavBuffer, guildId, userId, username);
            await axios.post(`${this.apiBaseUrl}/discord/audio`, form, { headers: form.getHeaders() });
        } catch (error) {
            console.error("[VoiceManager] API Error:", error.message);
        }
    }

    // what the brain needs to weigh a voice perception: who said it, whether it
    // knows them, and how many people are in the room with her
    speechForm(wavBuffer, guildId, userId, username) {
        const form = new FormData();
        form.append('file', wavBuffer, { filename: 'audio.wav', contentType: 'audio/wav' });
        form.append('username', username);
        form.append('user_id', userId);
        form.append('whitelisted', String(whitelist.has(userId)));
        form.append('listeners', String(this.listenerCount(guildId)));
        return form;
    }

    // humans in the call, Bea excluded: at one, everything said is said to her
    listenerCount(guildId) {
        const data = this.connections.get(guildId);
        const channelId = data && data.channelId;
        if (!channelId) return 0;
        try {
            const channel = this.client.channels.cache.get(channelId);
            if (!channel || !channel.members) return 0;
            return [...channel.members.values()].filter((m) => m.id !== this.client.user.id).length;
        } catch (e) {
            return 0;
        }
    }

    async displayNameOf(guildId, userId) {
        try {
            const guild = await this.client.guilds.fetch(guildId);
            const member = await guild.members.fetch(userId);
            return member.displayName;
        } catch (e) {
            console.error("Error fetching user:", e);
            return userId;
        }
    }

    // --- her voice, pushed from the brain ----------------------------------

    // tells the brain where she is and how many people are in there with her.
    // the brain never assumes: being dragged into a call is as real as joining one
    announceCall() {
        const guildId = this.currentGuild();
        const data = guildId ? this.connections.get(guildId) : null;
        if (!data) {
            this.link.send({ type: 'left' });
            return;
        }
        this.link.send({
            type: 'joined',
            channel_id: data.channelId,
            listeners: this.listenerCount(guildId),
        });
    }

    /**
     * one chunk of an utterance. the first chunk starts the playback, so sound
     * begins before the rest has even been synthesised.
     */
    playPushed(header, pcm) {
        const guildId = this.currentGuild();
        const data = guildId ? this.connections.get(guildId) : null;
        if (!data || !data.player) return;

        let speech = data.speech;
        if (!speech || speech.id !== header.utterance_id) {
            speech = this.openUtterance(guildId, header.utterance_id);
        }
        if (pcm && pcm.length) speech.source.write(pcm);
        if (header.last) speech.source.end();
    }

    openUtterance(guildId, utteranceId) {
        const data = this.connections.get(guildId);
        this.finishUtterance(guildId, 'stopped');

        const source = new PassThrough();
        const gain = new PcmGain((playedMs) => this.report(utteranceId, playedMs, 'playing'));
        source.pipe(gain);

        // raw is 48khz stereo s16le — exactly what the brain already sends, so
        // nothing here has to decode, resample or guess a format
        const resource = createAudioResource(gain, { inputType: StreamType.Raw });
        data.speech = { id: utteranceId, source, gain };
        data.player.play(resource);
        this.report(utteranceId, 0, 'playing');
        return data.speech;
    }

    finishUtterance(guildId, state) {
        const data = this.connections.get(guildId);
        if (!data || !data.speech) return;
        const { id, source, gain } = data.speech;
        data.speech = null;
        source.end();
        this.report(id, gain.playedMs, state);
    }

    /** fades her out and stops. the ramp is the difference between trailing off
     *  and being cut mid-word, and the report says how much the room actually got. */
    stopSpeaking(rampMs = 200) {
        const guildId = this.currentGuild();
        const data = guildId ? this.connections.get(guildId) : null;
        if (!data || !data.speech) return;

        data.speech.gain.rampTo(0, rampMs);
        setTimeout(() => {
            const still = this.connections.get(guildId);
            if (!still || !still.speech) return;
            this.finishUtterance(guildId, 'stopped');
            still.player.stop();
        }, rampMs);
    }

    /** turns her down without stopping her: someone said "sì sì", not "no aspetta" */
    duck(gain, rampMs = 250) {
        const guildId = this.currentGuild();
        const data = guildId ? this.connections.get(guildId) : null;
        if (!data || !data.speech) return;
        data.speech.gain.rampTo(gain, rampMs);
    }

    /** stops accepting more of this utterance; what is already queued plays out */
    cancelPending() {
        const guildId = this.currentGuild();
        const data = guildId ? this.connections.get(guildId) : null;
        if (data && data.speech) data.speech.source.end();
    }

    report(utteranceId, playedMs, state) {
        this.link.send({ type: 'playback', utterance_id: utteranceId, played_ms: playedMs, state });
    }

    // stereo 48khz s16le -> mono 16khz s16le. simple average + 3x decimation:
    // good enough for speech-to-text and roughly halves the bytes we ship.
    downsampleMono16k(pcmData) {
        const groupBytes = 12; // 3 stereo frames (3 * 2ch * 2 bytes)
        const outLen = Math.floor(pcmData.length / groupBytes) * 2;
        const out = Buffer.alloc(outLen);
        let oi = 0;
        for (let i = 0; i + 4 <= pcmData.length && oi + 2 <= outLen; i += groupBytes) {
            const l = pcmData.readInt16LE(i);
            const r = pcmData.readInt16LE(i + 2);
            out.writeInt16LE((l + r) >> 1, oi);
            oi += 2;
        }
        return out;
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
