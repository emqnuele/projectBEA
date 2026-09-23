/**
 * One person's turn, gathered out of the pieces discord delivers it in.
 *
 * Discord does not hand over an utterance. It opens a stream when a client
 * starts transmitting and closes it a moment after the client stops, and a
 * client stops whenever the speaker takes a breath. Every pause inside a
 * sentence used to end a stream, and each fragment went off to be transcribed
 * on its own — so "wait, no, I meant the other one" reached her as three
 * separate things somebody said, and she answered the first before hearing the
 * rest of it.
 *
 * So a turn is not a stream. A turn is held here until the person has actually
 * stopped for long enough to have finished, whatever discord did with the
 * socket in the meantime, and only then goes anywhere.
 *
 * The other thing this owns is what to do about somebody talking over her,
 * and that is a question about the two of them rather than about either one:
 * how long they have been talking *while she was*. Counting how long they have
 * been talking at all is what cut her off the instant she answered anybody
 * already mid-sentence, which in a call is simply what answering looks like.
 *
 * Pure: audio and a clock in, decisions out. It holds a buffer, it does not
 * hold a socket.
 */

const { createVoiceActivity, FRAME_MS, HANGOVER_MS } = require('./VoiceActivity');
const { BYTES_PER_MS, createDownsampler } = require('./Pcm');

// under this much actual voice a turn is a cough, a chair, a click: not words
const MIN_SPEECH_MS = 250;

/**
 * How much of the run-up to somebody talking is kept in front of their turn.
 *
 * Every packet used to be appended, from whenever the last turn was sent, and
 * the buffer was only ever emptied by sending one. So a turn arrived carrying
 * however long the room had been transmitting before anybody opened their
 * mouth — half a minute of it, in a room the gate never stopped listening to —
 * and two sentences a quarter of a minute apart reached her as one.
 *
 * The onset is sixty milliseconds long and a hard consonant lives inside it,
 * so the run-up is worth keeping. The rest of the room is not.
 */
const PREROLL_MS = 400;

/**
 * How long a turn can run before it is cut and sent as it stands. Somebody who
 * talks for a minute straight should reach her in pieces rather than as a
 * minute of silence followed by a minute of audio — and nothing that grows
 * with how long a person feels like talking should be unbounded in memory.
 */
const MAX_TURN_MS = 30000;

/**
 * How long without a packet before it is a gap in what somebody sends, rather
 * than the next packet still on its way.
 *
 * While somebody transmits, a packet lands every twenty milliseconds, and the
 * sweep lands between two of them whenever it likes. Every one of those used
 * to count as a silence heard with her not speaking: it zeroed the count of
 * how long they had been talking over her — so she was never ducked and never
 * stopped, however long they went on — reset a voice halfway through its
 * onset, and ran the clock ahead of the audio.
 */
const GAP_MS = 3 * FRAME_MS;

// what a sweep between two packets has to say about it: nothing
const NOTHING = Object.freeze({ duck: false, interrupt: false, released: false, ended: false });

function createSpeechBuffer(options = {}) {
    const {
        duckMs = 400,
        interruptMs = 4000,
        minSpeechMs = MIN_SPEECH_MS,
        maxTurnMs = MAX_TURN_MS,
        hangoverMs = HANGOVER_MS,
    } = options;

    const activity = createVoiceActivity({ hangoverMs });
    // one per speaker, because the filter in front of it carries the tail of
    // the last packet into the next one
    const downsample = createDownsampler();

    // what belongs to this turn, and is gone once it has been sent
    let chunks = [];
    let heldMs = 0;
    let voicedMs = 0;

    // and the last moments before it, kept rolling so that the start of a word
    // is not the first thing thrown away
    let preroll = [];
    let prerollMs = 0;

    // what belongs to this unbroken run of talking, which is usually the same
    // thing — except when somebody talks for so long that the turn is cut and
    // sent while they are still going. Re-ducking her at every cut, or telling
    // the brain twice that it was interrupted, is what keeping these together
    // would buy.
    let ducking = false;
    let pressed = false;
    let interrupted = false;
    let overheard = false;
    let started = false;

    // how long they have been talking *over her*, which is not how long they
    // have been talking. See `act`.
    let overlapMs = 0;

    let lastAt = null;
    // how much of the silence since the last packet the detector already has
    let counted = 0;

    function clearTurn() {
        chunks = [];
        heldMs = 0;
        voicedMs = 0;
    }

    function clearPreroll() {
        preroll = [];
        prerollMs = 0;
    }

    function clearRun() {
        ducking = false;
        pressed = false;
        interrupted = false;
        overheard = false;
        started = false;
        overlapMs = 0;
    }

    /**
     * Turns one answer from the detector into what the call should do about it.
     * `duck` and `interrupt` fire once each per turn; `released` says this
     * person has stopped leaning on her, which is not the same as her being
     * free to come back up — somebody else may still be talking.
     */
    function act(frame, beaSpeaking) {
        const report = { duck: false, interrupt: false, released: false, ended: false };

        if (frame.started && !started) {
            started = true;
            // read now, not when the stream opened: she may have started or
            // stopped talking in between, and acting on the stale answer is how
            // a reply to her gets filed as something merely overheard
            overheard = Boolean(beaSpeaking);
        }

        if (beaSpeaking && frame.speaking) {
            // seconds of somebody talking *over her*, counted from the moment
            // she opened her mouth and out of frames that were actually a voice.
            //
            // What was counted before was the length of *their* run, which
            // starts when they started. She decides to speak when she has
            // something to say, not when the room goes quiet, so answering
            // somebody already three seconds into a sentence met the threshold
            // on the first frame and cut her off inside twenty milliseconds.
            overlapMs += frame.voicedMs;
            if (!ducking && overlapMs >= duckMs) {
                ducking = true;
                report.duck = true;
            }
            if (!pressed && overlapMs >= interruptMs) {
                pressed = true;
                interrupted = true;
                report.interrupt = true;
            }
        } else if (!beaSpeaking) {
            // she has the floor to herself: there is nothing to talk over, and
            // the next thing she says starts the count again from nothing
            overlapMs = 0;
            pressed = false;
        }

        if (ducking && (!frame.speaking || !beaSpeaking)) {
            ducking = false;
            report.released = true;
        }

        if (frame.ended || heldMs >= maxTurnMs) report.ended = true;
        return report;
    }

    return {
        get open() {
            return started;
        },

        get voicedMs() {
            return voicedMs;
        },

        /** Decoded audio for this person, 48 khz stereo, straight off the wire. */
        push(pcm, { now = 0, beaSpeaking = false } = {}) {
            lastAt = now;
            counted = 0;
            const frame = activity.push(pcm);
            // kept at 16 khz mono because that is the only form it ever leaves
            // in, and holding half a minute of 48 khz stereo per person in the
            // call to throw five sixths of it away at the end is a waste
            const mono = downsample(pcm);
            const ms = pcm.length / BYTES_PER_MS;

            if (chunks.length || frame.started || frame.speaking) {
                // the run-up comes with them the moment they are believed
                if (!chunks.length) {
                    for (const held of preroll) {
                        chunks.push(held.pcm);
                        heldMs += held.ms;
                    }
                    clearPreroll();
                }
                chunks.push(mono);
                heldMs += ms;
            } else {
                preroll.push({ pcm: mono, ms });
                prerollMs += ms;
                while (preroll.length > 1 && prerollMs - preroll[0].ms >= PREROLL_MS) {
                    prerollMs -= preroll.shift().ms;
                }
            }

            voicedMs += frame.voicedMs;
            return act(frame, beaSpeaking);
        },

        /**
         * The sweep, looking at this person. When nothing has arrived for
         * longer than a packet takes, this is what ends a turn: it runs down
         * the hangover across the gaps discord leaves between one stream and
         * the next. Between two packets it has nothing to say.
         */
        gap(now, { beaSpeaking = false } = {}) {
            if (lastAt === null) lastAt = now;
            const idle = now - lastAt;
            if (idle < GAP_MS) return NOTHING;
            // the whole silence, once: from the last packet, and then only what
            // has passed since the sweep before
            const fresh = idle - counted;
            counted = idle;
            // a breath taken while talking over her is still talking over her
            return act(activity.silence(fresh), beaSpeaking);
        },

        /**
         * Everything said, ready to send — or null when it was never speech.
         * Either way the turn is over and the next one starts clean.
         */
        take() {
            const turn = voicedMs >= minSpeechMs
                ? { pcm: Buffer.concat(chunks), ms: Math.round(heldMs), voicedMs, overheard, interrupted }
                : null;
            clearTurn();
            // they may still be mid-sentence: this turn was cut for length, and
            // the rest of what they are saying belongs to the same run
            if (!activity.speaking) clearRun();
            return turn;
        },

        /** Somebody left mid-sentence: drop what they were saying. */
        abandon() {
            clearTurn();
            clearPreroll();
            clearRun();
            activity.reset();
            lastAt = null;
            counted = 0;
        },
    };
}

module.exports = { createSpeechBuffer, MIN_SPEECH_MS, MAX_TURN_MS, PREROLL_MS, GAP_MS };
