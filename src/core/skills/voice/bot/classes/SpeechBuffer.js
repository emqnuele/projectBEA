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
 * because that decision needs exactly the same signal: how long they have held
 * the floor *without stopping*. What was here before counted every loud block
 * since the stream opened and never put the count back, so a fan that cleared
 * the gate accumulated its way to an interruption in three seconds of nobody
 * saying anything.
 *
 * Pure: audio and a clock in, decisions out. It holds a buffer, it does not
 * hold a socket.
 */

const { createVoiceActivity, HANGOVER_MS } = require('./VoiceActivity');
const { BYTES_PER_MS, downsampleMono16k } = require('./Pcm');

// under this much actual voice a turn is a cough, a chair, a click: not words
const MIN_SPEECH_MS = 250;

/**
 * How long a turn can run before it is cut and sent as it stands. Somebody who
 * talks for a minute straight should reach her in pieces rather than as a
 * minute of silence followed by a minute of audio — and nothing that grows
 * with how long a person feels like talking should be unbounded in memory.
 */
const MAX_TURN_MS = 30000;

function createSpeechBuffer(options = {}) {
    const {
        duckMs = 400,
        interruptMs = 3000,
        minSpeechMs = MIN_SPEECH_MS,
        maxTurnMs = MAX_TURN_MS,
        hangoverMs = HANGOVER_MS,
    } = options;

    const activity = createVoiceActivity({ hangoverMs });

    // what belongs to this turn, and is gone once it has been sent
    let chunks = [];
    let heldMs = 0;
    let voicedMs = 0;

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

    let lastAt = null;

    function clearTurn() {
        chunks = [];
        heldMs = 0;
        voicedMs = 0;
    }

    function clearRun() {
        ducking = false;
        pressed = false;
        interrupted = false;
        overheard = false;
        started = false;
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

        if (frame.speaking && beaSpeaking) {
            if (!ducking && frame.speakingMs >= duckMs) {
                ducking = true;
                report.duck = true;
            }
            if (!pressed && frame.speakingMs >= interruptMs) {
                pressed = true;
                interrupted = true;
                report.interrupt = true;
            }
        }

        if (!frame.speaking && ducking) {
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
            const frame = activity.push(pcm);
            // kept at 16 khz mono because that is the only form it ever leaves
            // in, and holding half a minute of 48 khz stereo per person in the
            // call to throw five sixths of it away at the end is a waste
            chunks.push(downsampleMono16k(pcm));
            heldMs += pcm.length / BYTES_PER_MS;
            voicedMs += frame.voicedMs;
            return act(frame, beaSpeaking);
        },

        /**
         * Nothing has arrived for this person since the last call. This is what
         * ends a turn: it runs down the hangover across the gaps discord leaves
         * between one stream and the next.
         */
        gap(now) {
            if (lastAt === null) lastAt = now;
            const idle = now - lastAt;
            lastAt = now;
            return act(activity.silence(idle), false);
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
            clearRun();
            activity.reset();
            lastAt = null;
        },
    };
}

module.exports = { createSpeechBuffer, MIN_SPEECH_MS, MAX_TURN_MS };
