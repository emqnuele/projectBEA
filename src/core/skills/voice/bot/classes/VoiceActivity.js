/**
 * Deciding when somebody in the call is talking, from the samples themselves.
 *
 * What was here before was a noise gate: one fixed number on the loudness of a
 * block, and anything over it counted as speech. A desk fan clears it, a game
 * clears it, a hand on a mechanical keyboard clears it — and every one of those
 * ducked her mid-sentence, then interrupted her, then sent a few seconds of
 * room tone to be transcribed. A quiet speaker cleared none of it.
 *
 * The browser side of the dashboard fixed the same problem by looking at where
 * the energy sits instead of how much of it there is. It can read a spectrum
 * because it has an analyser node; here there is only raw pcm, so the same
 * question is asked with filters:
 *
 *  - **Where the energy is.** A two-pole band-pass across 200-3400 Hz, and the
 *    ratio of what survives it to what went in. Speech lives almost entirely
 *    inside that band, so it keeps most of itself; a fan is underneath it and
 *    hiss is above it, and both come out a fraction of what they were. The
 *    ratio does not care how loud the room is, which is the point.
 *  - **A noise floor that moves.** How far over *this person's own* background
 *    a sound has to climb, rather than over a number picked once. It follows a
 *    room getting quieter at once and a room getting louder slowly, and it is
 *    never updated while a voice is being heard — a voice must not raise the
 *    bar it is being measured against.
 *
 * The floor is also left alone across the gaps where discord sends nothing at
 * all. Those gaps are not silence anybody heard: they are the other client
 * deciding not to transmit, and treating them as a quiet room would wash out
 * everything learned about a loud one between two sentences.
 *
 * Pure: samples in, transitions out. The clock is the audio itself — twenty
 * milliseconds per frame consumed — so every case in the tests is a buffer you
 * can write down rather than a thing you have to sit in a call and try.
 */

const { SAMPLE_RATE, BYTES_PER_FRAME } = require('./Pcm');

// one opus frame's worth, which is also what the decoder hands over at a time
const FRAME_MS = 20;
const FRAME_BYTES = (SAMPLE_RATE / 1000) * FRAME_MS * BYTES_PER_FRAME;

// where speech lives. The low edge is under the usual 300 because a deep voice
// carries real weight down there, and losing it costs more than the extra
// rumble that comes in with it — the floor deals with rumble anyway.
const SPEECH_LOW_HZ = 200;
const SPEECH_HIGH_HZ = 3400;

/**
 * How much of a sound has to survive the band for it to be a voice, as a ratio
 * of the levels before and after. Measured, not guessed: against synthetic
 * tones and noise the band leaves a fan at 0.18, broadband noise at 0.27 and
 * the deepest voice worth worrying about at 0.40. Set between the last two and
 * nearer the noise, because letting a fan through costs one bad transcript and
 * rejecting a voice costs the turn.
 */
const MIN_FOCUS = 0.32;

// how far over the room's own noise the level has to climb to start, and back
// down to before it stops. Two numbers, so a voice sitting near the line does
// not switch on and off between syllables.
const ENTER_OVER_FLOOR = 2.2;
const EXIT_OVER_FLOOR = 1.35;

// ...and the same in absolute terms, because a client that transmits digital
// silence has a floor of zero and every ratio against it is meaningless
const ENTER_MARGIN = 200;
const EXIT_MARGIN = 100;

// how long a sound has to hold before it is somebody starting to talk. Shorter
// than the browser's, because discord's own client has already decided this is
// worth transmitting and a packet that arrives at all is halfway to evidence.
const ONSET_MS = 60;

/**
 * And how long a silence has to hold before they have finished.
 *
 * This is the number that used to be 100, inherited from how long discord waits
 * before closing a stream, and it is why a sentence with a breath in it arrived
 * as two. It is what a turn is now cut on, so the pause has to be longer than
 * one inside a sentence and shorter than one between people.
 */
const HANGOVER_MS = 500;

// how fast the floor follows the room: down at once, up slowly
const FLOOR_FALL = 0.25;
const FLOOR_RISE = 0.02;

/** A two-pole band-pass as a cascade of one-pole sections, sample by sample. */
function bandPass(lowHz, highHz) {
    const dt = 1 / SAMPLE_RATE;
    const highRc = 1 / (2 * Math.PI * lowHz);
    const lowRc = 1 / (2 * Math.PI * highHz);
    const hpGain = highRc / (highRc + dt);
    const lpGain = dt / (lowRc + dt);

    const hpIn = [0, 0];
    const hpOut = [0, 0];
    const lp = [0, 0];

    return (sample) => {
        let value = sample;
        for (let p = 0; p < 2; p += 1) {
            const out = hpGain * (hpOut[p] + value - hpIn[p]);
            hpIn[p] = value;
            hpOut[p] = out;
            value = out;
        }
        for (let p = 0; p < 2; p += 1) {
            lp[p] += lpGain * (value - lp[p]);
            value = lp[p];
        }
        return value;
    };
}

/**
 * @param minFocus   override for a call that needs to be more or less willing
 * @param onsetMs    how long a sound holds before it counts as a voice
 * @param hangoverMs how long a silence holds before the turn is over
 */
function createVoiceActivity(options = {}) {
    const {
        onsetMs = ONSET_MS,
        hangoverMs = HANGOVER_MS,
        minFocus = MIN_FOCUS,
    } = options;

    const filter = bandPass(SPEECH_LOW_HZ, SPEECH_HIGH_HZ);
    const samplesPerFrame = FRAME_BYTES / BYTES_PER_FRAME;

    let rest = Buffer.alloc(0);
    let clock = 0;
    // starts at nothing rather than at whatever arrives first. On an open
    // microphone the first frame is room tone and seeding from it is right; on
    // discord the first packet anybody ever sends is them talking, and seeding
    // from that sets the bar at their own voice and swallows the first thing
    // they say.
    let floor = 0;
    let speaking = false;
    let loudSince = null;
    let quietSince = null;
    let startedAt = null;

    /** One frame's loudness, and how much of it sits in the speech band. */
    function measure(block, offset) {
        let full = 0;
        let band = 0;
        for (let i = 0; i < samplesPerFrame; i += 1) {
            const at = offset + i * BYTES_PER_FRAME;
            const mono = (block.readInt16LE(at) + block.readInt16LE(at + 2)) / 2;
            const voiced = filter(mono);
            full += mono * mono;
            band += voiced * voiced;
        }
        const level = Math.sqrt(full / samplesPerFrame);
        return { level, focus: level > 0 ? Math.sqrt(band / samplesPerFrame) / level : 0 };
    }

    function report(extra) {
        return {
            speaking,
            started: false,
            ended: false,
            arming: !speaking && loudSince !== null,
            // how long this unbroken run of talking has been going, counted
            // from the first sound of it and not from the moment it was believed
            speakingMs: speaking && startedAt !== null ? clock - startedAt : 0,
            voicedMs: 0,
            level: 0,
            focus: 0,
            floor,
            ...extra,
        };
    }

    return {
        get speaking() {
            return speaking;
        },

        get floor() {
            return floor;
        },

        /**
         * Decoded audio, 48 khz stereo, any length. Whole frames are consumed
         * and a short tail is kept for the next call.
         *
         * `started` and `ended` are the transitions crossed while consuming it.
         * A buffer long enough to hold a whole turn would report only the last
         * of them; discord hands over twenty milliseconds at a time, so one
         * call can cross at most one.
         */
        push(pcm) {
            const block = rest.length ? Buffer.concat([rest, pcm]) : pcm;
            const usable = block.length - (block.length % FRAME_BYTES);
            rest = Buffer.from(block.subarray(usable));

            let started = false;
            let ended = false;
            let voicedMs = 0;
            let last = { level: 0, focus: 0 };

            for (let at = 0; at < usable; at += FRAME_BYTES) {
                last = measure(block, at);
                clock += FRAME_MS;

                const enter = Math.max(floor * ENTER_OVER_FLOOR, floor + ENTER_MARGIN);
                const exit = Math.max(floor * EXIT_OVER_FLOOR, floor + EXIT_MARGIN);
                const voiced = last.focus >= minFocus;
                const loud = last.level > enter && voiced;

                if (speaking) voicedMs += FRAME_MS;

                if (!speaking) {
                    // the floor is only what this person's room sounds like when
                    // they are not talking into it, so it learns from that alone
                    if (!loud) {
                        floor += (last.level - floor) * (last.level < floor ? FLOOR_FALL : FLOOR_RISE);
                        loudSince = null;
                    } else {
                        if (loudSince === null) loudSince = clock - FRAME_MS;
                        if (clock - loudSince >= onsetMs) {
                            speaking = true;
                            started = true;
                            startedAt = loudSince;
                            loudSince = null;
                            quietSince = null;
                        }
                    }
                } else if (last.level < exit || !voiced) {
                    if (quietSince === null) quietSince = clock - FRAME_MS;
                    if (clock - quietSince >= hangoverMs) {
                        speaking = false;
                        ended = true;
                        quietSince = null;
                        startedAt = null;
                    }
                } else {
                    quietSince = null;
                }
            }

            return report({ started, ended, voicedMs, level: last.level, focus: last.focus });
        },

        /**
         * A stretch where discord sent nothing: the other client stopped
         * transmitting. It runs the hangover down and nothing else — no samples
         * arrived, so there is nothing here to learn a noise floor from.
         */
        silence(ms) {
            if (!(ms > 0)) return report({});
            clock += ms;
            if (!speaking) {
                loudSince = null;
                return report({});
            }
            if (quietSince === null) quietSince = clock - ms;
            if (clock - quietSince < hangoverMs) return report({});
            speaking = false;
            quietSince = null;
            startedAt = null;
            return report({ ended: true });
        },

        /** Back to knowing nothing, for somebody who left and came back. */
        reset() {
            rest = Buffer.alloc(0);
            floor = 0;
            speaking = false;
            loudSince = null;
            quietSince = null;
            startedAt = null;
        },
    };
}

module.exports = {
    createVoiceActivity,
    FRAME_MS,
    FRAME_BYTES,
    ONSET_MS,
    HANGOVER_MS,
    MIN_FOCUS,
    SPEECH_LOW_HZ,
    SPEECH_HIGH_HZ,
};
