/**
 * Deciding when somebody is talking, from a spectrum.
 *
 * What was here before was a volume meter: one fixed threshold on the average
 * of every frequency bin, and a second and a half of silence before it believed
 * you had stopped. Both halves of that are wrong in the same way — it cannot
 * tell a voice from a sound. A desk fan holds the turn open forever, a keyboard
 * opens one, and the quiet tail of a real sentence closes one early.
 *
 * Two things fix most of it, and neither needs a model:
 *
 *  - **Where the energy is**, not how much there is. Speech puts most of its
 *    energy between 300 and 3400 Hz. A fan is almost entirely underneath that
 *    band and a keyboard is spread flat across everything, so the ratio between
 *    the speech band and the whole spectrum separates all three without caring
 *    how loud the room is.
 *  - **A noise floor that moves.** The threshold is relative to whatever this
 *    room has been sounding like, so the same numbers work in a quiet study and
 *    next to a running PC. It follows a room getting quieter at once and a room
 *    getting louder slowly, and it is never updated while she is being talked
 *    to — a voice must not raise the bar it is being measured against.
 *
 * That buys the hangover down from 1500 ms to 600, which is a second saved on
 * every single spoken turn. It is deliberately not lower: this reads energy,
 * not speech, so it cannot tell a pause in a sentence from the end of one the
 * way a neural detector can — 600 ms is comfortably past a within-sentence
 * pause and still most of the way to the shortest useful gap.
 *
 * Pure: bins in, transitions out. No microphone, no DOM, no timers — the clock
 * is passed in, which is what makes every case below a test rather than a
 * thing you have to stand in a room and try.
 */

// where speech lives. Under the first is rumble, over the second is hiss.
export const SPEECH_LOW_HZ = 300;
export const SPEECH_HIGH_HZ = 3400;

// How concentrated in the speech band the energy has to be. 1 is a flat
// spectrum — white noise, a keyboard, a door. Speech leaves most of the
// spectrum empty, so it lands far above this; a fan lands near zero.
export const MIN_FOCUS = 2.5;

// how far over the room's own noise the level has to climb to start, and back
// down to before it stops. Two numbers, so a voice sitting near the line does
// not switch on and off between syllables.
export const ENTER_OVER_FLOOR = 2.2;
export const EXIT_OVER_FLOOR = 1.35;

// ...and the same in absolute terms, because in a silent room the floor is zero
// and every ratio against it is meaningless
export const ENTER_MARGIN = 8;
export const EXIT_MARGIN = 4;

// how long a sound has to hold before it is somebody starting to talk. Long
// enough to throw away a key press, short enough not to be heard as a delay.
export const ONSET_MS = 90;

// and how long a silence has to hold before it is somebody having finished
export const HANGOVER_MS = 600;

// how fast the floor follows the room: down at once, up slowly. A fan that
// starts is absorbed in a few seconds; a voice never is, because the floor is
// not updated while she is hearing one.
const FLOOR_FALL = 0.25;
const FLOOR_RISE = 0.02;

function mean(bins, from, to) {
    let sum = 0;
    for (let i = from; i < to; i += 1) sum += bins[i];
    return sum / Math.max(1, to - from);
}

/**
 * @param sampleRate  the AudioContext's, used to turn hertz into bin indices
 * @param fftSize     the analyser's, same reason
 * @returns an object whose `push` takes one frame and answers what changed
 */
export function createVoiceActivity(options = {}) {
    const {
        sampleRate = 48000,
        fftSize = 256,
        onsetMs = ONSET_MS,
        hangoverMs = HANGOVER_MS,
        minFocus = MIN_FOCUS,
    } = options;

    const perBin = sampleRate / fftSize;
    const low = Math.max(1, Math.round(SPEECH_LOW_HZ / perBin));
    const high = Math.max(low + 1, Math.round(SPEECH_HIGH_HZ / perBin));

    let floor = null;
    let speaking = false;
    let loudSince = null;
    let quietSince = null;

    return {
        get floor() {
            return floor ?? 0;
        },

        get speaking() {
            return speaking;
        },

        /**
         * One frame of the analyser's byte spectrum.
         *
         * `arming` is the half-second-of-a-second between a sound starting and
         * it being confirmed as a voice. It is reported because a recorder
         * started only once the onset is confirmed has already missed the first
         * syllable — the caller starts on `arming` and throws the take away if
         * `started` never follows.
         */
        push(bins, now) {
            const level = mean(bins, low, Math.min(high, bins.length));
            const across = mean(bins, 0, bins.length);
            const focus = across > 0 ? level / across : 0;

            if (floor === null) floor = level;

            const enter = Math.max(floor * ENTER_OVER_FLOOR, floor + ENTER_MARGIN);
            const exit = Math.max(floor * EXIT_OVER_FLOOR, floor + EXIT_MARGIN);
            const voiced = focus >= minFocus;
            const loud = level > enter && voiced;
            const quiet = level < exit || !voiced;

            let started = false;
            let ended = false;

            if (!speaking) {
                // the floor is only what the room sounds like when nobody is
                // talking into it, so it learns from silence and nothing else
                if (!loud) {
                    const rate = level < floor ? FLOOR_FALL : FLOOR_RISE;
                    floor += (level - floor) * rate;
                    loudSince = null;
                } else {
                    if (loudSince === null) loudSince = now;
                    if (now - loudSince >= onsetMs) {
                        speaking = true;
                        started = true;
                        loudSince = null;
                        quietSince = null;
                    }
                }
            } else if (quiet) {
                if (quietSince === null) quietSince = now;
                if (now - quietSince >= hangoverMs) {
                    speaking = false;
                    ended = true;
                    quietSince = null;
                }
            } else {
                quietSince = null;
            }

            return {
                speaking,
                started,
                ended,
                arming: !speaking && loudSince !== null,
                level,
                focus,
                floor,
            };
        },

        /** Back to knowing nothing, for a microphone that was just re-opened. */
        reset() {
            floor = null;
            speaking = false;
            loudSince = null;
            quietSince = null;
        },
    };
}
