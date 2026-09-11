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
const { createSpeechBuffer } = require('./SpeechBuffer');
const { pcmToWav } = require('./Pcm');

// discord closes a receive stream this long after a client stops transmitting.
// It is kept short on purpose: what a turn is now gets decided by the hangover
// in SpeechBuffer, so there is no reason to hold a subscription open waiting.
const STREAM_END_MS = 200;

// how often a turn that has gone quiet is checked for being over. The hangover
// is half a second, so this costs at most a tenth of one on top of it.
const TICK_MS = 100;

// the fade-down while someone talks over her, the fade-back-up once they stop,
// and what she stops at. 0.25 is audible but gone quickly, and 200ms is short
// enough to feel immediate on both ramps
const DUCK_GAIN = 0.25;
const DUCK_RAMP_MS = 250;
const UNDUCK_RAMP_MS = 200;
const STOP_RAMP_MS = 200;

class VoiceManager {
    constructor(client) {
        this.client = client;
        this.connections = new Map(); // guildId -> connection data
        this.apiBaseUrl = config.BRAIN_API_URL;

        // two stages of being talked over: turn down, then stop
        this.DUCK_THRESHOLD_MS = config.DUCK_THRESHOLD_MS;
        this.INTERRUPT_THRESHOLD_MS = config.INTERRUPT_THRESHOLD_MS;

        // everyone currently leaning on her. She comes back up when it empties,
        // not when the first of them stops — in a call with three people the
        // other two are still talking
        this.ducking = new Set();

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
                subscriptions: new Map(), // userid -> opusstream
                speakers: new Map(),      // userid -> the turn they are taking
                tick: null,               // the sweep that notices one ending
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
            if (data.tick) clearInterval(data.tick);
            for (const stream of data.subscriptions.values()) {
                stream.destroy();
            }
            // whatever anybody was halfway through saying was said to a call
            // that no longer exists
            for (const speaker of data.speakers.values()) {
                speaker.buffer.abandon();
            }
            data.speakers.clear();
            this.ducking.clear();
            this.connections.delete(guildId);
        }
        this.announceCall();
    }

    listenToUsers(guildId) {
        const data = this.connections.get(guildId);
        // Ready fires again on a reconnect, and a second subscription would
        // hand every packet over twice
        if (!data || data.tick) return;

        const receiver = data.connection.receiver;

        // discord opens a stream per burst of transmission, not per sentence,
        // so this fires again every time somebody takes a breath. What it opens
        // is a subscription; the turn it belongs to is decided elsewhere.
        receiver.speaking.on('start', (userId) => {
            if (data.subscriptions.has(userId)) return;
            this.createStream(guildId, userId);
        });

        data.tick = setInterval(() => this.sweep(guildId), TICK_MS);
    }

    /** The turn of somebody who is talking, or about to be. */
    speakerFor(data, userId) {
        let speaker = data.speakers.get(userId);
        if (!speaker) {
            speaker = {
                buffer: createSpeechBuffer({
                    duckMs: this.DUCK_THRESHOLD_MS,
                    interruptMs: this.INTERRUPT_THRESHOLD_MS,
                }),
            };
            data.speakers.set(userId, speaker);
        }
        return speaker;
    }

    /**
     * Nothing arrived from anyone this tick, or not from everyone. A turn ends
     * on a silence, and a silence is the absence of packets — so it can only be
     * noticed by looking, never by being told.
     */
    sweep(guildId) {
        const data = this.connections.get(guildId);
        if (!data) return;
        const now = Date.now();
        for (const [userId, speaker] of data.speakers) {
            this.act(guildId, userId, speaker.buffer.gap(now));
        }
    }

    createStream(guildId, userId) {
        const data = this.connections.get(guildId);
        if (!data) return;

        const opusStream = data.connection.receiver.subscribe(userId, {
            end: { behavior: EndBehaviorType.AfterSilence, duration: STREAM_END_MS },
        });
        data.subscriptions.set(userId, opusStream);

        // decode opus to pcm (signed 16-bit little endian, 48khz, stereo)
        const decoder = new prism.opus.Decoder({ frameSize: 960, channels: 2, rate: 48000 });
        const pcmStream = opusStream.pipe(decoder);
        const speaker = this.speakerFor(data, userId);

        pcmStream.on('data', (chunk) => {
            // read her speaking state per chunk rather than once when the stream
            // opened: she can start or stop in the middle of somebody's sentence
            this.act(guildId, userId, speaker.buffer.push(chunk, {
                now: Date.now(),
                beaSpeaking: data.isSpeaking,
            }));
        });

        opusStream.on('error', (err) => {
            // `pipe` does not forward errors, so a stream that dies mid-burst
            // without this would take the whole process down
            console.error(`[VoiceManager] Receive stream error for ${userId}:`, err.message);
            close();
        });
        const close = () => {
            if (data.subscriptions.get(userId) === opusStream) data.subscriptions.delete(userId);
        };
        pcmStream.on('end', close);
        pcmStream.on('error', (err) => {
            console.error(`[VoiceManager] Stream error for ${userId}:`, err.message);
            close();
        });
    }

    /** What the call does about one answer from somebody's turn. */
    act(guildId, userId, report) {
        if (report.duck) {
            this.ducking.add(userId);
            console.log('[VoiceManager] Someone is talking over her — ducking');
            this.duck(DUCK_GAIN, DUCK_RAMP_MS);
        }

        if (report.interrupt) {
            console.log('[VoiceManager] Sustained speech — interrupting her');
            this.stopSpeaking(STOP_RAMP_MS);
            this.tellBrain('/interrupt');
        }

        if (report.released) {
            this.ducking.delete(userId);
            // only once the last of them has stopped: coming back up while
            // somebody else is still going would just duck her again
            if (this.ducking.size === 0) this.duck(1, UNDUCK_RAMP_MS);
        }

        // nothing above this is awaited, and an unhandled rejection here would
        // take the whole bot down over one turn that could not be delivered
        if (report.ended) {
            this.sendTurn(guildId, userId).catch((e) => {
                console.error('[VoiceManager] Could not deliver a turn:', e.message);
            });
        }
    }

    /** A turn that is over: transcribe it, or throw it away as room noise. */
    async sendTurn(guildId, userId) {
        const data = this.connections.get(guildId);
        const speaker = data && data.speakers.get(userId);
        if (!speaker) return;

        const turn = speaker.buffer.take();
        if (!turn) {
            console.log(`[VoiceManager] Nothing said by ${userId} — dropping the noise`);
            return;
        }

        const username = await this.displayNameOf(guildId, userId);
        const wav = pcmToWav(turn.pcm);

        // something said over her that never took the floor is something she
        // overheard, and overhearing must not start the clock on an answer
        const route = turn.overheard && !turn.interrupted ? '/voice/transcript' : '/discord/audio';
        console.log(`[VoiceManager] ${username}: ${turn.voicedMs}ms of speech -> ${route}`);

        try {
            const form = this.speechForm(wav, guildId, userId, username);
            await axios.post(`${this.apiBaseUrl}${route}`, form, { headers: form.getHeaders() });
        } catch (error) {
            console.error(`[VoiceManager] ${route} failed:`, error.message);
        }
    }

    // the brain is on the other end of a socket that can be down; a turn that
    // cannot be delivered is lost, and that must not take the call with it
    tellBrain(path) {
        axios.post(`${this.apiBaseUrl}${path}`).catch((e) => {
            console.error(`[VoiceManager] ${path} failed:`, e.message);
        });
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
    stopSpeaking(rampMs = STOP_RAMP_MS) {
        const guildId = this.currentGuild();
        const data = guildId ? this.connections.get(guildId) : null;
        if (!data || !data.speech) return;

        const speech = data.speech;
        speech.gain.rampTo(0, rampMs);
        // a new utterance can start inside the fade and must not be the one
        // this times out. It finishes only the utterance it faded, and only if
        // that utterance is still the one on the wire.
        setTimeout(() => {
            const still = this.connections.get(guildId);
            if (!still || still.speech !== speech) return;
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
}

module.exports = VoiceManager;
